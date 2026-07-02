"""
core/unet_model.py

Defines the PyTorch U-Net architecture for spatial land-cover forecasting.
"""

import torch
import torch.nn as nn


class DoubleConv(nn.Module):
    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(x)


class UNet(nn.Module):
    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.inc = DoubleConv(in_channels, 64)
        self.down1 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(64, 128))
        self.down2 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(128, 256))
        self.down3 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(256, 512))

        self.up1 = nn.ConvTranspose2d(512, 256, 2, stride=2)
        self.conv1 = DoubleConv(512, 256)
        self.up2 = nn.ConvTranspose2d(256, 128, 2, stride=2)
        self.conv2 = DoubleConv(256, 128)
        self.up3 = nn.ConvTranspose2d(128, 64, 2, stride=2)
        self.conv3 = DoubleConv(128, 64)

        self.outc = nn.Conv2d(64, out_channels, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)

        up1 = self.up1(x4)
        x_up1 = torch.cat([up1, x3], dim=1)
        conv1 = self.conv1(x_up1)

        up2 = self.up2(conv1)
        x_up2 = torch.cat([up2, x2], dim=1)
        conv2 = self.conv2(x_up2)

        up3 = self.up3(conv2)
        x_up3 = torch.cat([up3, x1], dim=1)
        conv3 = self.conv3(x_up3)

        return self.outc(conv3)


from torchvision.models import resnet34, ResNet34_Weights

class ResNet34UNet(nn.Module):
    def __init__(self, in_channels: int = 22, out_channels: int = 6, pretrained: bool = True):
        super().__init__()
        # Load official ResNet34 base model
        weights = ResNet34_Weights.DEFAULT if pretrained else None
        base = resnet34(weights=weights)

        # 2D Input channels projection layer (22 -> 3 channels)
        # Compresses our 22 features into 3 channels to preserve ResNet pre-trained weights
        self.input_projection = nn.Conv2d(in_channels, 3, kernel_size=3, padding=1, bias=False)

        # Share Encoder layers from ResNet34 base
        self.encoder_conv1 = base.conv1
        self.encoder_bn1 = base.bn1
        self.encoder_relu = base.relu
        self.encoder_maxpool = base.maxpool

        self.layer1 = base.layer1  # 64 channels, downby 4
        self.layer2 = base.layer2  # 128 channels, downby 8
        self.layer3 = base.layer3  # 256 channels, downby 16
        self.layer4 = base.layer4  # 512 channels, downby 32

        # Decoder layers matched to ResNet channel dimensions
        self.up1 = nn.ConvTranspose2d(512, 256, kernel_size=2, stride=2)
        self.conv1 = DoubleConv(512, 256)

        self.up2 = nn.ConvTranspose2d(256, 128, kernel_size=2, stride=2)
        self.conv2 = DoubleConv(256, 128)

        self.up3 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
        self.conv3 = DoubleConv(128, 64)

        self.up4 = nn.ConvTranspose2d(64, 64, kernel_size=2, stride=2)
        self.conv4 = DoubleConv(128, 64)

        self.outc = nn.Conv2d(64, out_channels, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Step 1: Compress 22 channels down to 3
        x_proj = self.input_projection(x)          # (B, 3, H, W)
        x_c1 = self.encoder_conv1(x_proj)          # (B, 64, H/2, W/2)
        x_bn1 = self.encoder_bn1(x_c1)
        x1 = self.encoder_relu(x_bn1)              # (B, 64, H/2, W/2) - Skip 4

        # Step 2: Encoder downsampling passes
        x_mp = self.encoder_maxpool(x1)            # (B, 64, H/4, W/4)
        x2 = self.layer1(x_mp)                     # (B, 64, H/4, W/4) - Skip 3
        x3 = self.layer2(x2)                       # (B, 128, H/8, W/8) - Skip 2
        x4 = self.layer3(x3)                       # (B, 256, H/16, W/16) - Skip 1
        x5 = self.layer4(x4)                       # (B, 512, H/32, W/32)

        # Step 3: Decoder upsampling passes with skip concatenations
        up1 = self.up1(x5)                         # (B, 256, H/16, W/16)
        x_up1 = torch.cat([up1, x4], dim=1)        # (B, 512, H/16, W/16)
        c1 = self.conv1(x_up1)                     # (B, 256, H/16, W/16)

        up2 = self.up2(c1)                         # (B, 128, H/8, W/8)
        x_up2 = torch.cat([up2, x3], dim=1)        # (B, 256, H/8, W/8)
        c2 = self.conv2(x_up2)                     # (B, 128, H/8, W/8)

        up3 = self.up3(c2)                         # (B, 64, H/4, W/4)
        x_up3 = torch.cat([up3, x2], dim=1)        # (B, 128, H/4, W/4)
        c3 = self.conv3(x_up3)                     # (B, 64, H/4, W/4)

        up4 = self.up4(c3)                         # (B, 64, H/2, W/2)
        x_up4 = torch.cat([up4, x1], dim=1)        # (B, 128, H/2, W/2)
        c4 = self.conv4(x_up4)                     # (B, 64, H/2, W/2)

        # Step 4: Map back to classes and interpolate up to match input coordinates
        out = self.outc(c4)
        out = nn.functional.interpolate(out, size=x.shape[2:], mode="bilinear", align_corners=True)
        return out

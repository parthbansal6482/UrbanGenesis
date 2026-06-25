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

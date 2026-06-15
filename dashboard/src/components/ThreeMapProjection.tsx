"use client";

import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

interface ThreeMapProjectionProps {
  beforeImageUrl: string | null;
  afterImageUrl: string | null;
  opacity: number;
  isMask: boolean;
  sliderValue: number; // 0 (100% before) to 100 (100% after)
}

export default function ThreeMapProjection({
  beforeImageUrl,
  afterImageUrl,
  opacity,
  isMask,
  sliderValue,
}: ThreeMapProjectionProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(false);
  const materialsRef = useRef<{ before: THREE.MeshPhongMaterial; after: THREE.MeshPhongMaterial } | null>(null);

  // Update slider/wipe position and opacity dynamically without rebuilding the scene
  useEffect(() => {
    if (materialsRef.current) {
      const { before, after } = materialsRef.current;
      before.opacity = opacity;
      after.opacity = opacity;

      // In a 3D split-wipe, we can update the shader or just control visibility
      // Since we are building a premium slider, let's control their material opacity
      // Or we can adjust a custom clipping plane!
      // To make it look extremely premium, let's use ThreeJS clipping planes to perform a true 3D split-wipe transition!
      // A local clipping plane will clip the "before" mesh from one side and the "after" mesh from the other!
      // This is a master-class in WebGL!
    }
  }, [opacity]);

  // Handle local clipping planes
  const clipPlaneBeforeRef = useRef<THREE.Plane | null>(null);
  const clipPlaneAfterRef = useRef<THREE.Plane | null>(null);

  useEffect(() => {
    // sliderValue is 0 to 100. Let's map it to plane X coordinate: -2.5 to 2.5 (since plane width is 5)
    if (clipPlaneBeforeRef.current && clipPlaneAfterRef.current) {
      const planeWidth = 5;
      const xOffset = ((sliderValue / 100) - 0.5) * planeWidth;
      
      // Before plane is visible on the LEFT of the wipe line (X < xOffset)
      // Normal points LEFT (-1, 0, 0), constant is xOffset
      clipPlaneBeforeRef.current.constant = -xOffset;

      // After plane is visible on the RIGHT of the wipe line (X > xOffset)
      // Normal points RIGHT (1, 0, 0), constant is xOffset
      clipPlaneAfterRef.current.constant = xOffset;
    }
  }, [sliderValue]);

  useEffect(() => {
    if (!containerRef.current) return;

    const width = containerRef.current.clientWidth || 500;
    const height = containerRef.current.clientHeight || 400;

    setLoading(true);

    // Scene
    const scene = new THREE.Scene();
    scene.background = null;

    // Camera
    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
    camera.position.set(0, 4.5, 7.5);

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.localClippingEnabled = true; // Enable local clipping planes!
    containerRef.current.appendChild(renderer.domElement);

    // Controls (Tilting & Panning)
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.rotateSpeed = 0.6;
    controls.minDistance = 4;
    controls.maxDistance = 12;
    controls.maxPolarAngle = Math.PI / 2 - 0.08; // Don't let camera go below floor
    controls.enablePan = false;

    // Pedestal / Table Base
    const pedestalGeo = new THREE.BoxGeometry(5.4, 0.25, 5.4);
    const pedestalMat = new THREE.MeshPhysicalMaterial({
      color: 0x1e293b, // Slate 800
      roughness: 0.3,
      metalness: 0.8,
      transparent: true,
      opacity: 0.9,
      transmission: 0.2,
      thickness: 1.0,
    });
    const pedestal = new THREE.Mesh(pedestalGeo, pedestalMat);
    pedestal.position.y = -0.155;
    scene.add(pedestal);

    // Pedestal subtle glowing border
    const gridHelper = new THREE.GridHelper(5.4, 10, 0x059669, 0x334155);
    gridHelper.position.y = -0.02;
    scene.add(gridHelper);

    // Clipping planes for the before/after swipe
    // Plane normals point opposite to each other
    const clipPlaneBefore = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0);
    const clipPlaneAfter = new THREE.Plane(new THREE.Vector3(1, 0, 0), 0);
    clipPlaneBeforeRef.current = clipPlaneBefore;
    clipPlaneAfterRef.current = clipPlaneAfter;

    // 3D Plane for textures
    const planeGeo = new THREE.PlaneGeometry(5, 5);

    // Create default/placeholder solid color materials
    const beforeMat = new THREE.MeshPhongMaterial({
      color: 0xe2e8f0,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: opacity,
      clippingPlanes: [clipPlaneBefore],
      shininess: 30,
    });

    const afterMat = new THREE.MeshPhongMaterial({
      color: 0xcbd5e1,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: opacity,
      clippingPlanes: [clipPlaneAfter],
      shininess: 30,
    });

    materialsRef.current = { before: beforeMat, after: afterMat };

    const beforeMesh = new THREE.Mesh(planeGeo, beforeMat);
    beforeMesh.rotation.x = -Math.PI / 2; // Flat on the pedestal
    beforeMesh.position.y = 0.01; // Slightly above pedestal to prevent z-fighting
    scene.add(beforeMesh);

    const afterMesh = new THREE.Mesh(planeGeo, afterMat);
    afterMesh.rotation.x = -Math.PI / 2;
    afterMesh.position.y = 0.015; // Slightly above before mesh to prevent z-fighting
    scene.add(afterMesh);

    // Dynamic swipe boundary line
    const boundaryGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0.02, -2.5),
      new THREE.Vector3(0, 0.02, 2.5),
    ]);
    const boundaryMat = new THREE.LineBasicMaterial({
      color: 0x059669, // Emerald 600
      linewidth: 3,
      transparent: true,
      opacity: 0.8,
    });
    const boundaryLine = new THREE.Line(boundaryGeo, boundaryMat);
    scene.add(boundaryLine);

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.65);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.85);
    dirLight.position.set(2, 6, 4);
    scene.add(dirLight);

    const pointLight = new THREE.PointLight(0x059669, 0.5, 10);
    pointLight.position.set(0, 3, 0);
    scene.add(pointLight);

    // Texture loading helper
    const textureLoader = new THREE.TextureLoader();
    textureLoader.setCrossOrigin("anonymous");

    const loadTextureWithFallback = (
      url: string | null,
      material: THREE.MeshPhongMaterial,
      onComplete: () => void
    ) => {
      if (!url) {
        material.map = null;
        material.needsUpdate = true;
        onComplete();
        return;
      }

      // Prepend API origin if relative
      const finalUrl = url.startsWith("http") ? url : `http://localhost:8000${url}`;

      const image = new Image();
      image.crossOrigin = "anonymous";
      image.onload = () => {
        let finalCanvas: HTMLCanvasElement | HTMLImageElement = image;

        if (isMask) {
          // Process mask black pixels to transparent
          const canvas = document.createElement("canvas");
          canvas.width = image.width;
          canvas.height = image.height;
          const ctx = canvas.getContext("2d");
          if (ctx) {
            ctx.drawImage(image, 0, 0);
            const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const data = imgData.data;
            for (let i = 0; i < data.length; i += 4) {
              const r = data[i];
              const g = data[i + 1];
              const b = data[i + 2];
              // If it's pure black or extremely close to it (e.g. background class 0)
              if (r === 0 && g === 0 && b === 0) {
                data[i + 3] = 0; // Transparent alpha
              }
            }
            ctx.putImageData(imgData, 0, 0);
            finalCanvas = canvas;
          }
        }

        const texture = new THREE.CanvasTexture(finalCanvas);
        texture.colorSpace = THREE.SRGBColorSpace;
        material.map = texture;
        material.color.setHex(0xffffff); // remove fallback gray tint
        material.needsUpdate = true;
        onComplete();
      };
      
      image.onerror = (err) => {
        console.error("Texture load failed for", finalUrl, err);
        material.map = null;
        material.color.setHex(0xfca5a5); // tint light red on error
        material.needsUpdate = true;
        onComplete();
      };

      image.src = finalUrl;
    };

    // Load textures
    let loadedCount = 0;
    const checkLoaded = () => {
      loadedCount++;
      if (loadedCount >= 2) {
        setLoading(false);
      }
    };

    loadTextureWithFallback(beforeImageUrl, beforeMat, checkLoaded);
    loadTextureWithFallback(afterImageUrl, afterMat, checkLoaded);

    // Resize Handler
    const handleResize = () => {
      if (!containerRef.current) return;
      const w = containerRef.current.clientWidth;
      const h = containerRef.current.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", handleResize);

    // Animation Loop
    let animationFrameId: number;
    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);

      // Wobble pedestal slightly for tactile premium feel
      pedestal.rotation.y = 0.03 * Math.sin(performance.now() * 0.0006);

      // Update slider wipe line position in 3D
      const planeWidth = 5;
      const xOffset = ((sliderValue / 100) - 0.5) * planeWidth;
      boundaryLine.position.x = xOffset;

      controls.update();
      renderer.render(scene, camera);
    };

    animate();

    // Clean up
    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", handleResize);
      if (renderer.domElement) {
        renderer.domElement.remove();
      }
      scene.clear();
      renderer.dispose();
    };
  }, [beforeImageUrl, afterImageUrl, isMask]); // Re-run if image URLs or mask setting changes

  return (
    <div className="relative w-full h-full flex items-center justify-center bg-slate-900 rounded-xl overflow-hidden border border-slate-800 shadow-md">
      {/* Visual stats header inside WebGL Card */}
      <div className="absolute top-4 left-4 right-4 flex justify-between items-center pointer-events-none z-10">
        <span className="bg-slate-950/80 backdrop-blur-md border border-slate-800 text-[10px] text-slate-400 font-mono px-2.5 py-1 rounded-full uppercase tracking-wider">
          3D Plane Projection
        </span>
        {loading && (
          <span className="bg-emerald-950/80 backdrop-blur-md border border-emerald-800 text-[10px] text-emerald-400 font-mono px-2.5 py-1 rounded-full animate-pulse">
            Syncing Satellites...
          </span>
        )}
      </div>

      {/* Grid overlay */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:20px_20px] pointer-events-none" />

      {/* ThreeJS Container */}
      <div
        ref={containerRef}
        className="w-full h-full min-h-[350px] md:min-h-[420px] cursor-grab active:cursor-grabbing"
      />

      {/* Wipe slider indicators */}
      <div className="absolute bottom-4 left-4 right-4 flex justify-between text-[11px] font-mono text-slate-500 pointer-events-none">
        <span>← BEFORE</span>
        <span>AFTER →</span>
      </div>
    </div>
  );
}

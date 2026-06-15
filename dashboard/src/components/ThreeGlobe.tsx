"use client";

import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

interface ZoneData {
  key: string;
  name: string;
  bbox: number[];
  center: number[];
  latest_grade: string;
  latest_abi: number;
  overall_abi_change_pct: number;
  cropland_loss_ha: number;
  encroachment_alert: boolean;
}

interface ThreeGlobeProps {
  zones: ZoneData[];
  selectedZoneKey: string | null;
  onSelectZone: (key: string) => void;
}

export default function ThreeGlobe({ zones, selectedZoneKey, onSelectZone }: ThreeGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const selectedZoneRef = useRef<string | null>(selectedZoneKey);
  const pinsGroupRef = useRef<THREE.Group | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);

  // Keep ref up to date to avoid re-triggering effect
  useEffect(() => {
    selectedZoneRef.current = selectedZoneKey;
    if (selectedZoneKey && cameraRef.current && controlsRef.current) {
      // Find the selected zone coordinates
      const zone = zones.find((z) => z.key === selectedZoneKey);
      if (zone) {
        const [lat, lon] = zone.center;
        const R = 5; // Globe radius
        const phi = (90 - lat) * (Math.PI / 180);
        const theta = (lon + 180) * (Math.PI / 180);
        
        const targetX = -R * Math.sin(phi) * Math.sin(theta);
        const targetY = R * Math.cos(phi);
        const targetZ = R * Math.sin(phi) * Math.cos(theta);

        // Position camera slightly further out in the same direction
        const zoomFactor = 2.2;
        const camX = targetX * zoomFactor;
        const camY = targetY * zoomFactor;
        const camZ = targetZ * zoomFactor;

        // Smoothly animate camera and controls target
        const duration = 1500;
        const startCam = cameraRef.current.position.clone();
        const startTarget = controlsRef.current.target.clone();
        const endTarget = new THREE.Vector3(targetX, targetY, targetZ);
        const endCam = new THREE.Vector3(camX, camY, camZ);
        
        const startTime = performance.now();
        
        const animateZoom = (now: number) => {
          const elapsed = now - startTime;
          const progress = Math.min(elapsed / duration, 1);
          // Ease out cubic
          const ease = 1 - Math.pow(1 - progress, 3);
          
          if (cameraRef.current && controlsRef.current) {
            cameraRef.current.position.lerpVectors(startCam, endCam, ease);
            controlsRef.current.target.lerpVectors(startTarget, endTarget, ease);
            controlsRef.current.update();
            
            if (progress < 1) {
              requestAnimationFrame(animateZoom);
            }
          }
        };
        
        requestAnimationFrame(animateZoom);
      }
    }
  }, [selectedZoneKey, zones]);

  useEffect(() => {
    if (!containerRef.current) return;

    const width = containerRef.current.clientWidth || 400;
    const height = containerRef.current.clientHeight || 400;

    // Scene
    const scene = new THREE.Scene();
    scene.background = null; // transparent background for landing page blend

    // Camera
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    camera.position.set(0, 5, 12);
    cameraRef.current = camera;

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    containerRef.current.appendChild(renderer.domElement);

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.rotateSpeed = 0.8;
    controls.minDistance = 6.5;
    controls.maxDistance = 20;
    controls.enablePan = false;
    controlsRef.current = controls;

    // Group for entire Globe (globe + grid + pins) to rotate together
    const globeGroup = new THREE.Group();
    scene.add(globeGroup);

    // Globe Radius
    const R = 5;

    // 1. Globe Core (Glassmorphic look)
    const globeGeo = new THREE.SphereGeometry(R, 64, 64);
    const globeMat = new THREE.MeshPhysicalMaterial({
      color: 0x0f172a, // Slate 900
      roughness: 0.2,
      metalness: 0.1,
      transparent: true,
      opacity: 0.65,
      transmission: 0.3,
      thickness: 1.2,
      ior: 1.4,
      clearcoat: 0.3,
      clearcoatRoughness: 0.1,
    });
    const globeCore = new THREE.Mesh(globeGeo, globeMat);
    globeGroup.add(globeCore);

    // 2. Wireframe / Grid Shell
    const wireframeGeo = new THREE.SphereGeometry(R + 0.01, 36, 18);
    const wireframeMat = new THREE.MeshBasicMaterial({
      color: 0x059669, // Emerald 600
      wireframe: true,
      transparent: true,
      opacity: 0.12,
    });
    const wireframeShell = new THREE.Mesh(wireframeGeo, wireframeMat);
    globeGroup.add(wireframeShell);

    // 3. Horizontal Grid Lines (Latitude circles)
    const lineMat = new THREE.LineBasicMaterial({
      color: 0xe2e8f0, // Slate 200
      transparent: true,
      opacity: 0.08,
    });
    for (let i = -8; i <= 8; i++) {
      const y = (i / 9) * R;
      const r = Math.sqrt(R * R - y * y);
      const ringGeo = new THREE.BufferGeometry();
      const points = [];
      for (let j = 0; j <= 64; j++) {
        const theta = (j / 64) * Math.PI * 2;
        points.push(new THREE.Vector3(Math.cos(theta) * r, y, Math.sin(theta) * r));
      }
      ringGeo.setFromPoints(points);
      const ring = new THREE.Line(ringGeo, lineMat);
      globeGroup.add(ring);
    }

    // 4. Atmosphere Glow Effect
    const glowGeo = new THREE.SphereGeometry(R + 0.3, 32, 32);
    // Standard back-side glow shader
    const glowMat = new THREE.ShaderMaterial({
      vertexShader: `
        varying vec3 vNormal;
        void main() {
          vNormal = normalize(normalMatrix * normal);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        varying vec3 vNormal;
        void main() {
          float intensity = pow(0.6 - dot(vNormal, vec3(0, 0, 1.0)), 2.5);
          gl_FragColor = vec4(0.05, 0.58, 0.41, 1.0) * intensity * 0.4; // Emerald glow
        }
      `,
      side: THREE.BackSide,
      blending: THREE.AdditiveBlending,
      transparent: true,
      depthWrite: false,
    });
    const glowShell = new THREE.Mesh(glowGeo, glowMat);
    scene.add(glowShell);

    // 5. Orbit Rings (To look premium / astronomical)
    const orbitRingGeo = new THREE.RingGeometry(R + 1.2, R + 1.25, 64);
    const orbitRingMat = new THREE.MeshBasicMaterial({
      color: 0x059669,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.1,
    });
    const orbitRing = new THREE.Mesh(orbitRingGeo, orbitRingMat);
    orbitRing.rotation.x = Math.PI / 2.3;
    globeGroup.add(orbitRing);

    // 6. Pins Group
    const pinsGroup = new THREE.Group();
    globeGroup.add(pinsGroup);
    pinsGroupRef.current = pinsGroup;

    // Helper to add a pin
    const pinObjects: THREE.Object3D[] = [];
    const pinToZoneMap = new Map<THREE.Object3D, string>();

    zones.forEach((zone) => {
      const [lat, lon] = zone.center;
      
      // Spherical Conversion
      const phi = (90 - lat) * (Math.PI / 180);
      const theta = (lon + 180) * (Math.PI / 180);

      const x = -R * Math.sin(phi) * Math.sin(theta);
      const y = R * Math.cos(phi);
      const z = R * Math.sin(phi) * Math.cos(theta);

      // Create Pin Anchor
      const pinAnchor = new THREE.Group();
      pinAnchor.position.set(x, y, z);

      // Orient pin outward from center
      const pinDirection = new THREE.Vector3(x, y, z).normalize();
      const up = new THREE.Vector3(0, 1, 0);
      const quaternion = new THREE.Quaternion().setFromUnitVectors(up, pinDirection);
      pinAnchor.quaternion.copy(quaternion);

      // Pin Color: Red if critical alert active, Green if stable
      const pinColor = zone.encroachment_alert ? 0xdc2626 : 0x059669;

      // Pin Cone/Needle pointing to center
      const coneGeo = new THREE.ConeGeometry(0.12, 0.45, 8);
      coneGeo.translate(0, 0.225, 0); // shift bottom of cone to origin
      const coneMat = new THREE.MeshPhongMaterial({
        color: pinColor,
        shininess: 80,
        emissive: pinColor,
        emissiveIntensity: 0.35,
      });
      const cone = new THREE.Mesh(coneGeo, coneMat);
      cone.rotation.x = Math.PI; // point down
      pinAnchor.add(cone);

      // Pulsing Base Ring below pin
      const ringGeometry = new THREE.RingGeometry(0.18, 0.24, 16);
      const ringMaterial = new THREE.MeshBasicMaterial({
        color: pinColor,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.8,
      });
      const baseRing = new THREE.Mesh(ringGeometry, ringMaterial);
      baseRing.rotation.x = Math.PI / 2;
      pinAnchor.add(baseRing);

      // Store animation properties on base ring
      baseRing.userData = { scaleProgress: 0.0, baseOpacity: 0.8 };

      pinsGroup.add(pinAnchor);
      pinObjects.push(cone); // We will raycast against the cone
      pinToZoneMap.set(cone, zone.key);
    });

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight1.position.set(5, 10, 7);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x059669, 0.4);
    dirLight2.position.set(-5, -5, -5);
    scene.add(dirLight2);

    // Raycasting for clicks
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const handleCanvasClick = (event: MouseEvent) => {
      // Get click position relative to canvas
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(pinObjects);

      if (intersects.length > 0) {
        const hitObject = intersects[0].object;
        const zoneKey = pinToZoneMap.get(hitObject);
        if (zoneKey) {
          onSelectZone(zoneKey);
        }
      }
    };

    renderer.domElement.addEventListener("click", handleCanvasClick);

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
    const clock = new THREE.Clock();

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);

      const delta = clock.getDelta();
      const elapsedTime = clock.getElapsedTime();

      // 1. Slow idle rotation if no zone is focused
      if (!selectedZoneRef.current) {
        globeGroup.rotation.y += 0.05 * delta;
      } else {
        // Slow orbit wobble
        globeGroup.rotation.y += 0.005 * delta;
      }

      // 2. Pulse Pin Base Rings
      pinsGroup.children.forEach((pinGroup) => {
        const ring = pinGroup.children[1] as THREE.Mesh;
        if (ring) {
          ring.userData.scaleProgress += 1.5 * delta;
          if (ring.userData.scaleProgress > 1.0) {
            ring.userData.scaleProgress = 0.0;
          }
          const scale = 1.0 + ring.userData.scaleProgress * 1.5;
          ring.scale.set(scale, scale, 1);
          
          const mat = ring.material as THREE.MeshBasicMaterial;
          if (mat) {
            mat.opacity = (1.0 - ring.userData.scaleProgress) * ring.userData.baseOpacity;
          }
        }

        // Slight hover wobble for pins
        const cone = pinGroup.children[0] as THREE.Mesh;
        if (cone) {
          cone.position.y = 0.08 * Math.sin(elapsedTime * 3 + cone.id);
        }
      });

      controls.update();
      renderer.render(scene, camera);
    };

    animate();

    // Clean up
    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", handleResize);
      if (renderer.domElement) {
        renderer.domElement.removeEventListener("click", handleCanvasClick);
        renderer.domElement.remove();
      }
      scene.clear();
      renderer.dispose();
    };
  }, [zones, onSelectZone]);

  return (
    <div className="relative w-full h-full flex items-center justify-center">
      {/* Decorative radial overlay */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_40%,rgba(248,250,252,0.65)_100%)] pointer-events-none" />
      
      {/* ThreeJS Container */}
      <div ref={containerRef} className="w-full h-full min-h-[350px] md:min-h-[450px] cursor-grab active:cursor-grabbing" />
      
      {/* Instruction hint overlay */}
      <div className="absolute bottom-4 left-4 right-4 bg-white/70 backdrop-blur-xs border border-slate-200/80 px-4 py-2.5 rounded-lg text-center text-xs text-slate-500 font-medium shadow-xs pointer-events-none max-w-sm mx-auto">
        👆 Drag to rotate 3D Earth • Scroll to zoom • Click a pulsing pin to inspect zone
      </div>
    </div>
  );
}

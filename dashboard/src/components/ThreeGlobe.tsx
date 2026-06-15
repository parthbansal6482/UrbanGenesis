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

  // Maintain ref to track selected zone without re-triggering base effect
  useEffect(() => {
    selectedZoneRef.current = selectedZoneKey;
    if (selectedZoneKey && cameraRef.current && controlsRef.current) {
      const zone = zones.find((z) => z.key === selectedZoneKey);
      if (zone) {
        const [lat, lon] = zone.center;
        const R = 5;
        const phi = (90 - lat) * (Math.PI / 180);
        const theta = (lon + 180) * (Math.PI / 180);
        
        const targetX = -R * Math.sin(phi) * Math.sin(theta);
        const targetY = R * Math.cos(phi);
        const targetZ = R * Math.sin(phi) * Math.cos(theta);

        const zoomFactor = 2.0;
        const camX = targetX * zoomFactor;
        const camY = targetY * zoomFactor;
        const camZ = targetZ * zoomFactor;

        const duration = 1200;
        const startCam = cameraRef.current.position.clone();
        const startTarget = controlsRef.current.target.clone();
        const endTarget = new THREE.Vector3(targetX, targetY, targetZ);
        const endCam = new THREE.Vector3(camX, camY, camZ);
        
        const startTime = performance.now();
        
        const animateZoom = (now: number) => {
          const elapsed = now - startTime;
          const progress = Math.min(elapsed / duration, 1);
          const ease = 1 - Math.pow(1 - progress, 3); // Ease out cubic
          
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

    // Use parent bounding rect to avoid 0px initialization bug
    const rect = containerRef.current.getBoundingClientRect();
    const width = rect.width || 500;
    const height = rect.height || 450;

    // Scene
    const scene = new THREE.Scene();
    scene.background = null;

    // Camera
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    camera.position.set(0, 4, 11);
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
    controls.rotateSpeed = 0.7;
    controls.minDistance = 6.0;
    controls.maxDistance = 15;
    controls.enablePan = false;
    controlsRef.current = controls;

    // Main Group
    const globeGroup = new THREE.Group();
    scene.add(globeGroup);

    const R = 5;

    // --- PROCEDURAL WORLD TEXTURE GENERATION ---
    const generateDottedMapTexture = (): THREE.CanvasTexture => {
      const texWidth = 1024;
      const texHeight = 512;

      const tempCanvas = document.createElement("canvas");
      tempCanvas.width = texWidth;
      tempCanvas.height = texHeight;
      const tempCtx = tempCanvas.getContext("2d");
      if (!tempCtx) return new THREE.CanvasTexture(tempCanvas);

      const mapLon = (lon: number) => ((lon + 180) / 360) * texWidth;
      const mapLat = (lat: number) => ((90 - lat) / 180) * texHeight;

      // Fill Ocean Base (Black)
      tempCtx.fillStyle = "#000000";
      tempCtx.fillRect(0, 0, texWidth, texHeight);

      // Draw Land (White)
      tempCtx.fillStyle = "#ffffff";
      
      const drawPolygon = (pts: number[][]) => {
        tempCtx.beginPath();
        pts.forEach(([lon, lat], idx) => {
          const x = mapLon(lon);
          const y = mapLat(lat);
          if (idx === 0) tempCtx.moveTo(x, y);
          else tempCtx.lineTo(x, y);
        });
        tempCtx.closePath();
        tempCtx.fill();
      };

      // Simplified global continents polygons
      const landPolygons = [
        // North America
        [[-168, 65], [-120, 70], [-60, 75], [-50, 50], [-80, 25], [-100, 15], [-105, 20], [-90, 15], [-80, 8]],
        // South America
        [[-80, 10], [-40, -10], [-35, -5], [-70, -55], [-75, -45]],
        // Africa
        [[-17, 15], [15, 30], [30, 30], [50, 10], [40, -30], [20, -35], [10, -10]],
        // Europe & Asia (Eurasia)
        [[-10, 60], [30, 70], [60, 75], [120, 75], [170, 65], [140, 35], [120, 10], [80, 10], [45, 15], [35, 30], [10, 35]],
        // India detailed polygon
        [[68, 24], [72, 31], [78, 31], [88, 22], [82, 10], [77, 8], [72, 12]],
        // Australia
        [[113, -25], [150, -15], [150, -35], [115, -35]],
        // Greenland
        [[-60, 80], [-30, 75], [-40, 60], [-55, 60]]
      ];

      landPolygons.forEach(drawPolygon);

      // Render dots onto output canvas
      const mainCanvas = document.createElement("canvas");
      mainCanvas.width = texWidth;
      mainCanvas.height = texHeight;
      const ctx = mainCanvas.getContext("2d");
      if (!ctx) return new THREE.CanvasTexture(mainCanvas);

      ctx.clearRect(0, 0, texWidth, texHeight);

      const imgData = tempCtx.getImageData(0, 0, texWidth, texHeight);
      const pixels = imgData.data;

      const dotSpacing = 8;
      ctx.fillStyle = "#059669"; // Emerald 600

      for (let y = 0; y < texHeight; y += dotSpacing) {
        for (let x = 0; x < texWidth; x += dotSpacing) {
          const index = (y * texWidth + x) * 4;
          if (pixels[index] > 200) {
            ctx.beginPath();
            ctx.arc(x, y, 1.8, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }

      const canvasTexture = new THREE.CanvasTexture(mainCanvas);
      canvasTexture.wrapS = THREE.RepeatWrapping;
      canvasTexture.wrapT = THREE.ClampToEdgeWrapping;
      return canvasTexture;
    };

    // --- GLOBE SPHERES ---
    // 1. Dotted Continent Shell (Outer sphere)
    const mapTexture = generateDottedMapTexture();
    const outerGeo = new THREE.SphereGeometry(R, 64, 64);
    const outerMat = new THREE.MeshPhongMaterial({
      map: mapTexture,
      transparent: true,
      opacity: 0.85,
      color: 0xffffff,
      side: THREE.DoubleSide,
      depthWrite: true,
      shininess: 10,
    });
    const outerShell = new THREE.Mesh(outerGeo, outerMat);
    globeGroup.add(outerShell);

    // 2. Liquid Frosted Glass Water Core (Inner sphere)
    const innerGeo = new THREE.SphereGeometry(R - 0.04, 64, 64);
    const innerMat = new THREE.MeshPhysicalMaterial({
      color: 0xf1f5f9, // Light Slate 100
      roughness: 0.15,
      metalness: 0.05,
      transparent: true,
      opacity: 0.75,
      transmission: 0.9,
      thickness: 1.5,
      ior: 1.45,
    });
    const innerSphere = new THREE.Mesh(innerGeo, innerMat);
    globeGroup.add(innerSphere);

    // 3. Holographic grid outline (translucent)
    const gridGeo = new THREE.SphereGeometry(R + 0.02, 30, 15);
    const gridMat = new THREE.MeshBasicMaterial({
      color: 0x94a3b8, // Slate 400
      wireframe: true,
      transparent: true,
      opacity: 0.06,
    });
    const gridMesh = new THREE.Mesh(gridGeo, gridMat);
    globeGroup.add(gridMesh);

    // 4. Subtle orbital data ring
    const orbitRingGeo = new THREE.RingGeometry(R + 1.0, R + 1.04, 64);
    const orbitRingMat = new THREE.MeshBasicMaterial({
      color: 0x059669,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.08,
    });
    const orbitRing = new THREE.Mesh(orbitRingGeo, orbitRingMat);
    orbitRing.rotation.x = Math.PI / 2.2;
    globeGroup.add(orbitRing);

    // --- PINS & LABELS ---
    const pinsGroup = new THREE.Group();
    globeGroup.add(pinsGroup);
    pinsGroupRef.current = pinsGroup;

    const pinObjects: THREE.Object3D[] = [];
    const pinToZoneMap = new Map<THREE.Object3D, string>();

    // Billboard Text Label Creator
    const createLabelSprite = (text: string) => {
      const labelCanvas = document.createElement("canvas");
      labelCanvas.width = 180;
      labelCanvas.height = 48;
      const lCtx = labelCanvas.getContext("2d");
      if (lCtx) {
        // Rounded card background
        lCtx.fillStyle = "rgba(15, 23, 42, 0.82)"; // Slate 900
        lCtx.beginPath();
        lCtx.roundRect(0, 0, 180, 36, 6);
        lCtx.fill();

        // Label text
        lCtx.fillStyle = "#ffffff";
        lCtx.font = "bold 11px system-ui, -apple-system, sans-serif";
        lCtx.textAlign = "center";
        lCtx.textBaseline = "middle";
        lCtx.fillText(text, 90, 18);
      }

      const tex = new THREE.CanvasTexture(labelCanvas);
      const spriteMat = new THREE.SpriteMaterial({ map: tex, transparent: true });
      const sprite = new THREE.Sprite(spriteMat);
      sprite.scale.set(1.1, 0.3, 1);
      return sprite;
    };

    const convertLatLngToVector3 = (lat: number, lon: number, radius: number) => {
      const phi = (90 - lat) * (Math.PI / 180);
      const theta = (lon + 180) * (Math.PI / 180);
      return new THREE.Vector3(
        -radius * Math.sin(phi) * Math.sin(theta),
        radius * Math.cos(phi),
        radius * Math.sin(phi) * Math.cos(theta)
      );
    };

    zones.forEach((zone) => {
      const [lat, lon] = zone.center;
      const pinPos = convertLatLngToVector3(lat, lon, R);

      const pinAnchor = new THREE.Group();
      pinAnchor.position.copy(pinPos);

      // Point pin outward from sphere center
      const pinDirection = pinPos.clone().normalize();
      const up = new THREE.Vector3(0, 1, 0);
      const quaternion = new THREE.Quaternion().setFromUnitVectors(up, pinDirection);
      pinAnchor.quaternion.copy(quaternion);

      const pinColor = zone.encroachment_alert ? 0xdc2626 : 0x059669;

      // Needle Cone pointing to sphere
      const coneGeo = new THREE.ConeGeometry(0.1, 0.4, 8);
      coneGeo.translate(0, 0.2, 0);
      const coneMat = new THREE.MeshPhongMaterial({
        color: pinColor,
        emissive: pinColor,
        emissiveIntensity: 0.4,
        shininess: 90,
      });
      const cone = new THREE.Mesh(coneGeo, coneMat);
      cone.rotation.x = Math.PI;
      pinAnchor.add(cone);

      // Pulsing Base Ring
      const ringGeo = new THREE.RingGeometry(0.14, 0.2, 16);
      const ringMat = new THREE.MeshBasicMaterial({
        color: pinColor,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.8,
      });
      const baseRing = new THREE.Mesh(ringGeo, ringMat);
      baseRing.rotation.x = Math.PI / 2;
      pinAnchor.add(baseRing);

      baseRing.userData = { scaleProgress: 0.0, baseOpacity: 0.8 };

      pinsGroup.add(pinAnchor);
      pinObjects.push(cone);
      pinToZoneMap.set(cone, zone.key);

      // Floating billboard label above the pin
      const labelText = zone.name
        .replace(" Agricultural Zone", "")
        .replace(" Peripheral", "")
        .replace(" Farmland", "")
        .replace(" Agricultural Buffer Zone", "");
      const labelSprite = createLabelSprite(labelText);
      labelSprite.position.set(pinPos.x * 1.12, pinPos.y * 1.12, pinPos.z * 1.12);
      scene.add(labelSprite); // added directly to scene so rotation of globe doesn't warp text orientation
      
      // Keep reference to labelSprite on pinGroup to update position during rotation
      pinAnchor.userData = { labelSprite, pinPos };
    });

    // --- CURVED DATA FLOW ARCS ---
    // Render curved flow lines connecting Bengaluru (HQ) to other active farmlands
    const bengaluruZone = zones.find((z) => z.key === "bengaluru");
    if (bengaluruZone) {
      const [bLat, bLon] = bengaluruZone.center;
      const startPos = convertLatLngToVector3(bLat, bLon, R);

      zones.forEach((zone) => {
        if (zone.key === "bengaluru") return;
        const [zLat, zLon] = zone.center;
        const endPos = convertLatLngToVector3(zLat, zLon, R);

        // Arch control point calculation
        const midPoint = new THREE.Vector3().addVectors(startPos, endPos).multiplyScalar(0.5);
        const dist = startPos.distanceTo(endPos);
        const norm = new THREE.Vector3().addVectors(startPos, endPos).normalize();
        midPoint.add(norm.multiplyScalar(dist * 0.2)); // arch height factor

        const curve = new THREE.QuadraticBezierCurve3(startPos, endPos, midPoint);
        const curvePoints = curve.getPoints(24);
        const arcGeo = new THREE.BufferGeometry().setFromPoints(curvePoints);
        const arcMat = new THREE.LineBasicMaterial({
          color: 0x94a3b8, // Slate 400
          transparent: true,
          opacity: 0.22,
        });
        const arcLine = new THREE.Line(arcGeo, arcMat);
        globeGroup.add(arcLine);
      });
    }

    // --- LIGHTING ---
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambientLight);

    const sunLight = new THREE.DirectionalLight(0xffffff, 0.9);
    sunLight.position.set(6, 12, 8);
    scene.add(sunLight);

    const fillLight = new THREE.DirectionalLight(0x059669, 0.25);
    fillLight.position.set(-6, -4, -6);
    scene.add(fillLight);

    // --- INTERACTION / RAYCASTING ---
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const handleCanvasClick = (event: MouseEvent) => {
      const bounds = renderer.domElement.getBoundingClientRect();
      mouse.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
      mouse.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(pinObjects);

      if (intersects.length > 0) {
        const hit = intersects[0].object;
        const key = pinToZoneMap.get(hit);
        if (key) {
          onSelectZone(key);
        }
      }
    };

    // Hover effect to change cursor to pointer
    const handleMouseMove = (event: MouseEvent) => {
      const bounds = renderer.domElement.getBoundingClientRect();
      mouse.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
      mouse.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(pinObjects);

      if (intersects.length > 0) {
        renderer.domElement.style.cursor = "pointer";
      } else {
        renderer.domElement.style.cursor = "grab";
      }
    };

    renderer.domElement.addEventListener("click", handleCanvasClick);
    renderer.domElement.addEventListener("mousemove", handleMouseMove);

    // Resize observer to prevent layout size initialization bug
    const resizeObserver = new ResizeObserver((entries) => {
      if (!entries || entries.length === 0) return;
      const { width: w, height: h } = entries[0].contentRect;
      if (w > 0 && h > 0) {
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
      }
    });
    resizeObserver.observe(containerRef.current);

    // --- ANIMATION LOOP ---
    let frameId: number;
    const clock = new THREE.Clock();

    const animate = () => {
      frameId = requestAnimationFrame(animate);

      const delta = clock.getDelta();
      const time = clock.getElapsedTime();

      // 1. Rotate globe
      if (!selectedZoneRef.current) {
        globeGroup.rotation.y += 0.04 * delta;
      } else {
        globeGroup.rotation.y += 0.004 * delta;
      }

      // 2. Animate pins & base rings
      pinsGroup.children.forEach((pinAnchor) => {
        // Animate pulsing base ring
        const baseRing = pinAnchor.children[1] as THREE.Mesh;
        if (baseRing) {
          baseRing.userData.scaleProgress += 1.4 * delta;
          if (baseRing.userData.scaleProgress > 1) {
            baseRing.userData.scaleProgress = 0;
          }
          const s = 1.0 + baseRing.userData.scaleProgress * 1.6;
          baseRing.scale.set(s, s, 1);
          
          const mat = baseRing.material as THREE.MeshBasicMaterial;
          if (mat) {
            mat.opacity = (1.0 - baseRing.userData.scaleProgress) * baseRing.userData.baseOpacity;
          }
        }

        // Animate floating wobble on pin needle
        const needle = pinAnchor.children[0] as THREE.Mesh;
        if (needle) {
          needle.position.y = 0.06 * Math.sin(time * 3 + needle.id);
        }

        // Project floating labels in sync with globe rotation
        const labelSprite = pinAnchor.userData.labelSprite as THREE.Sprite;
        const localPos = pinAnchor.userData.pinPos as THREE.Vector3;
        if (labelSprite && localPos) {
          // Compute world coordinates of pin after group rotations
          const worldPos = localPos.clone().applyMatrix4(globeGroup.matrixWorld);
          // Position label slightly further out from the rotated vector
          labelSprite.position.copy(worldPos.multiplyScalar(1.12));
        }
      });

      controls.update();
      renderer.render(scene, camera);
    };

    animate();

    return () => {
      cancelAnimationFrame(frameId);
      resizeObserver.disconnect();
      if (renderer.domElement) {
        renderer.domElement.removeEventListener("click", handleCanvasClick);
        renderer.domElement.removeEventListener("mousemove", handleMouseMove);
        renderer.domElement.remove();
      }
      // Clean up labels added directly to scene
      scene.children.forEach((child) => {
        if (child instanceof THREE.Sprite) {
          scene.remove(child);
        }
      });
      scene.clear();
      renderer.dispose();
    };
  }, [zones, onSelectZone]);

  return (
    <div className="relative w-full h-full flex items-center justify-center">
      {/* Visual Atmosphere backdrop gradient */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.7)_0%,rgba(248,250,252,0.9)_100%)] pointer-events-none" />
      
      {/* Canvas Mount */}
      <div ref={containerRef} className="w-full h-full min-h-[380px] md:min-h-[460px] cursor-grab active:cursor-grabbing" />

      {/* Desk widget instruction tag */}
      <div className="absolute bottom-4 left-4 right-4 bg-white/70 backdrop-blur-xs border border-slate-200/60 px-4 py-2 rounded-lg text-center text-[10px] font-mono text-slate-500 uppercase tracking-widest pointer-events-none max-w-sm mx-auto shadow-xs">
        Drag Earth • Scroll zoom • Click marker to audit
      </div>
    </div>
  );
}

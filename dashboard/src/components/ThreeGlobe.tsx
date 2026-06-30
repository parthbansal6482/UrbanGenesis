"use client";
// Three.js r184 compatible

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

// Map geo-coordinates to scene 3D space
// Longitude [68, 90] -> X [-5.5, 5.5]
// Latitude [8, 26] -> Z [4.5, -4.5]
const LON_MIN = 68, LON_MAX = 90;
const LAT_MIN = 8, LAT_MAX = 26;
const SCENE_W = 11;
const SCENE_H = 9;

function mapLon(lon: number): number {
  return ((lon - LON_MIN) / (LON_MAX - LON_MIN) - 0.5) * SCENE_W;
}

function mapLat(lat: number): number {
  return -((lat - LAT_MIN) / (LAT_MAX - LAT_MIN) - 0.5) * SCENE_H;
}


export default function ThreeGlobe({ zones, selectedZoneKey, onSelectZone }: ThreeGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const pinMeshes = useRef<THREE.Mesh[]>([]);
  const pinToZone = useRef<Map<THREE.Mesh, string>>(new Map());
  const selectedRef = useRef<string | null>(selectedZoneKey);

  // Camera animation on selection change
  useEffect(() => {
    selectedRef.current = selectedZoneKey;
    if (!cameraRef.current || !controlsRef.current) return;

    const cam = cameraRef.current;
    const ctrl = controlsRef.current;

    let targetCam: THREE.Vector3;
    let targetLook: THREE.Vector3;

    if (selectedZoneKey) {
      const zone = zones.find(z => z.key === selectedZoneKey);
      if (zone) {
        const [lat, lon] = zone.center;
        const x = mapLon(lon);
        const z = mapLat(lat);
        targetCam = new THREE.Vector3(x, 5.5, z + 5);
        targetLook = new THREE.Vector3(x, 0, z);
      } else {
        return;
      }
    } else {
      targetCam = new THREE.Vector3(0, 8, 10);
      targetLook = new THREE.Vector3(0, 0, 0);
    }

    const startCam = cam.position.clone();
    const startLook = ctrl.target.clone();
    const duration = 900;
    const t0 = performance.now();

    const animateCamera = (now: number) => {
      const progress = Math.min((now - t0) / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3);
      cam.position.lerpVectors(startCam, targetCam, ease);
      ctrl.target.lerpVectors(startLook, targetLook, ease);
      ctrl.update();
      if (progress < 1) requestAnimationFrame(animateCamera);
    };

    requestAnimationFrame(animateCamera);
  }, [selectedZoneKey, zones]);

  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const rect = el.getBoundingClientRect();
    const W = rect.width || 720;
    const H = rect.height || 520;

    // =========================================================
    // SCENE SETUP
    // =========================================================
    const scene = new THREE.Scene();
    scene.background = null;
    scene.fog = new THREE.FogExp2(0x050c14, 0.03);

    const camera = new THREE.PerspectiveCamera(38, W / H, 0.1, 200);
    camera.position.set(0, 8, 10);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(W, H);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    el.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.04;
    controls.rotateSpeed = 0.45;
    controls.minDistance = 4;
    controls.maxDistance = 18;
    controls.maxPolarAngle = Math.PI / 2.15;
    controls.enablePan = false;
    controlsRef.current = controls;

    // =========================================================
    // BASE PLATFORM — a light angled terrain slab
    // =========================================================
    const baseGeo = new THREE.BoxGeometry(SCENE_W + 2, 0.25, SCENE_H + 2);
    const baseMat = new THREE.MeshStandardMaterial({
      color: 0xe2e8f0,
      roughness: 0.7,
      metalness: 0.3,
    });
    const baseMesh = new THREE.Mesh(baseGeo, baseMat);
    baseMesh.position.y = -0.125;
    baseMesh.receiveShadow = true;
    scene.add(baseMesh);

    // =========================================================
    // PROCEDURAL TERRAIN TEXTURE for the map surface
    // =========================================================
    const texSize = 1024;
    const terrainCanvas = document.createElement("canvas");
    terrainCanvas.width = texSize;
    terrainCanvas.height = texSize;
    const tc = terrainCanvas.getContext("2d")!;

    // Light base
    tc.fillStyle = "#e2e8f0";
    tc.fillRect(0, 0, texSize, texSize);

    // Grid overlay — thin emerald lines
    tc.strokeStyle = "rgba(5,150,105,0.06)";
    tc.lineWidth = 0.8;
    const gridDivs = 22;
    for (let i = 0; i <= gridDivs; i++) {
      const x = (i / gridDivs) * texSize;
      const y = (i / gridDivs) * texSize;
      tc.beginPath(); tc.moveTo(x, 0); tc.lineTo(x, texSize); tc.stroke();
      tc.beginPath(); tc.moveTo(0, y); tc.lineTo(texSize, y); tc.stroke();
    }

    // India-ish coastline silhouette — simplified polygon fill
    const indiaPolygon = [
      [68.5, 23.5], [69.5, 22.5], [70.2, 20.8], [72.0, 19.5],
      [72.5, 18.0], [72.8, 16.2], [73.5, 14.8], [74.3, 12.8],
      [75.0, 10.8], [77.0, 8.5], [78.5, 9.0], [79.5, 12.0],
      [80.0, 13.5], [80.1, 15.8], [81.5, 17.2], [83.0, 18.0],
      [85.0, 19.5], [87.0, 21.5], [88.5, 22.0], [87.5, 24.0],
      [84.0, 25.5], [79.0, 26.0], [74.0, 25.8], [71.0, 25.0],
      [68.5, 23.5],
    ];

    const toTex = (lon: number, lat: number): [number, number] => {
      const px = ((lon - LON_MIN) / (LON_MAX - LON_MIN)) * texSize;
      const py = (1 - (lat - LAT_MIN) / (LAT_MAX - LAT_MIN)) * texSize;
      return [px, py];
    };

    // Land mass fill
    tc.beginPath();
    indiaPolygon.forEach(([lon, lat], i) => {
      const [px, py] = toTex(lon, lat);
      if (i === 0) tc.moveTo(px, py);
      else tc.lineTo(px, py);
    });
    tc.closePath();

    const landGrad = tc.createLinearGradient(0, 0, texSize, texSize);
    landGrad.addColorStop(0, "rgba(248,250,252,0.95)");
    landGrad.addColorStop(0.5, "rgba(255,255,255,0.95)");
    landGrad.addColorStop(1, "rgba(241,245,249,0.95)");
    tc.fillStyle = landGrad;
    tc.fill();

    // Land border glow
    tc.strokeStyle = "rgba(5,150,105,0.25)";
    tc.lineWidth = 2.5;
    tc.stroke();

    // State border approximations — subtle lines
    const stateLines = [
      [[73, 15.5], [76, 12.5]], // Karnataka coast
      [[76, 20], [80, 22]], // Telangana north
      [[74, 17], [77, 19]], // Maharashtra-Goa
    ] as [number, number][][];

    tc.strokeStyle = "rgba(15,23,42,0.08)";
    tc.lineWidth = 1;
    stateLines.forEach(pts => {
      tc.beginPath();
      pts.forEach(([lon, lat], i) => {
        const [px, py] = toTex(lon, lat);
        if (i === 0) tc.moveTo(px, py);
        else tc.lineTo(px, py);
      });
      tc.stroke();
    });

    // Coordinate labels on texture
    tc.fillStyle = "rgba(51,90,130,0.6)";
    tc.font = "bold 11px monospace";
    for (let lon = 70; lon <= 88; lon += 4) {
      const [px] = toTex(lon, LAT_MIN + 1.5);
      tc.fillText(`${lon}°E`, px - 12, texSize - 14);
    }
    for (let lat = 10; lat <= 24; lat += 4) {
      const [, py] = toTex(LON_MIN + 0.5, lat);
      tc.fillText(`${lat}°N`, 6, py + 4);
    }

    const terrainTex = new THREE.CanvasTexture(terrainCanvas);

    // Map surface plane
    const mapGeo = new THREE.PlaneGeometry(SCENE_W, SCENE_H, 1, 1);
    const mapMat = new THREE.MeshStandardMaterial({
      map: terrainTex,
      roughness: 0.85,
      metalness: 0.1,
      transparent: true,
      opacity: 0.95,
    });
    const mapMesh = new THREE.Mesh(mapGeo, mapMat);
    mapMesh.rotation.x = -Math.PI / 2;
    mapMesh.position.y = 0.01;
    mapMesh.receiveShadow = true;
    scene.add(mapMesh);

    // =========================================================
    // INDIA OUTLINE — glowing 3D line on surface
    // =========================================================
    const outlinePoints3D = indiaPolygon.map(([lon, lat]) =>
      new THREE.Vector3(mapLon(lon), 0.04, mapLat(lat))
    );
    const outlineCurve = new THREE.CatmullRomCurve3(outlinePoints3D, true);
    const outlinePts = outlineCurve.getPoints(120);
    const outlineGeo = new THREE.BufferGeometry().setFromPoints(outlinePts);
    const outlineMat = new THREE.LineBasicMaterial({
      color: 0x059669,
      transparent: true,
      opacity: 0.5,
    });
    scene.add(new THREE.Line(outlineGeo, outlineMat));

    // =========================================================
    // DATA STREAM LINES between zones (arched bezier)
    // =========================================================
    const hqZone = zones.find(z => z.key === "bengaluru");
    if (hqZone) {
      const [hqLat, hqLon] = hqZone.center;
      const hqPos = new THREE.Vector3(mapLon(hqLon), 0.06, mapLat(hqLat));

      zones.filter(z => z.key !== "bengaluru").forEach(zone => {
        const [lat, lon] = zone.center;
        const endPos = new THREE.Vector3(mapLon(lon), 0.06, mapLat(lat));
        const mid = new THREE.Vector3().addVectors(hqPos, endPos).multiplyScalar(0.5);
        mid.y = hqPos.distanceTo(endPos) * 0.22;

        const streamCurve = new THREE.QuadraticBezierCurve3(hqPos, mid, endPos);
        const streamPts = streamCurve.getPoints(48);
        const streamGeo = new THREE.BufferGeometry().setFromPoints(streamPts);
        const streamMat = new THREE.LineBasicMaterial({
          color: (zone.latest_grade === "F" || zone.latest_grade === "C") ? 0xdc2626 : 0x059669,
          transparent: true,
          opacity: 0.18,
        });
        scene.add(new THREE.Line(streamGeo, streamMat));
      });
    }

    // =========================================================
    // ZONE PINS
    // =========================================================
    const pins: THREE.Mesh[] = [];
    const pinMap = new Map<THREE.Mesh, string>();

    zones.forEach(zone => {
      const [lat, lon] = zone.center;
      const x = mapLon(lon);
      const z = mapLat(lat);
      const isHighRisk = zone.latest_grade === "F" || zone.latest_grade === "C";
      const color = isHighRisk ? 0xdc2626 : 0x059669;
      const emissive = isHighRisk ? 0xdc2626 : 0x059669;

      // ---- Glow base disc ----
      const discGeo = new THREE.CircleGeometry(0.4, 32);
      const discMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.12,
        side: THREE.DoubleSide,
      });
      const disc = new THREE.Mesh(discGeo, discMat);
      disc.rotation.x = -Math.PI / 2;
      disc.position.set(x, 0.015, z);
      scene.add(disc);

      // ---- Ring pulse ----
      const ringGeo = new THREE.RingGeometry(0.25, 0.35, 32);
      const ringMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.7,
        side: THREE.DoubleSide,
      });
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.rotation.x = -Math.PI / 2;
      ring.position.set(x, 0.02, z);
      ring.userData = { type: "ring", t: Math.random() * Math.PI * 2, zone: zone.key };
      scene.add(ring);

      // ---- Vertical column ----
      const colH = isHighRisk ? 1.6 : 0.9;
      const colGeo = new THREE.CylinderGeometry(0.06, 0.06, colH, 12);
      const colMat = new THREE.MeshStandardMaterial({
        color,
        emissive,
        emissiveIntensity: 0.55,
        roughness: 0.3,
        metalness: 0.6,
        transparent: true,
        opacity: 0.85,
      });
      const col = new THREE.Mesh(colGeo, colMat);
      col.position.set(x, colH / 2 + 0.02, z);
      col.castShadow = true;
      scene.add(col);

      // ---- Pin cap (hexagonal prism) ----
      const capGeo = new THREE.CylinderGeometry(0.18, 0.18, 0.08, 6);
      const capMat = new THREE.MeshStandardMaterial({
        color,
        emissive,
        emissiveIntensity: 0.8,
        roughness: 0.2,
        metalness: 0.8,
      });
      const cap = new THREE.Mesh(capGeo, capMat);
      cap.position.set(x, colH + 0.07, z);
      cap.castShadow = true;
      scene.add(cap);

      // Raycasting target = cap mesh
      pins.push(cap);
      pinMap.set(cap, zone.key);

      // ---- Floating billboard label ----
      const labelCanvas = document.createElement("canvas");
      labelCanvas.width = 200;
      labelCanvas.height = 56;
      const lCtx = labelCanvas.getContext("2d")!;

      // Background pill
      lCtx.fillStyle = isHighRisk ? "rgba(220,38,38,0.92)" : "rgba(5,150,105,0.92)";
      lCtx.beginPath();
      lCtx.roundRect(0, 0, 200, 46, 8);
      lCtx.fill();

      // Border
      lCtx.strokeStyle = isHighRisk ? "rgba(248,113,113,0.7)" : "rgba(52,211,153,0.7)";
      lCtx.lineWidth = 1.5;
      lCtx.beginPath();
      lCtx.roundRect(1, 1, 198, 44, 8);
      lCtx.stroke();

      // Zone short name
      const shortName = zone.name
        .replace(" Agricultural Zone", "")
        .replace(" Agricultural Buffer Zone", "")
        .replace(" Peripheral", "")
        .replace(" Farmland", "");
      lCtx.fillStyle = "#ffffff";
      lCtx.font = "bold 11px monospace";
      lCtx.textAlign = "center";
      lCtx.fillText(shortName.toUpperCase(), 100, 18);

      // Grade
      lCtx.fillStyle = "rgba(255,255,255,0.75)";
      lCtx.font = "9px monospace";
      lCtx.fillText(`Grade: ${zone.latest_grade}  ABI: ${zone.latest_abi.toFixed(2)}`, 100, 34);

      const labelTex = new THREE.CanvasTexture(labelCanvas);
      const labelMat = new THREE.SpriteMaterial({ map: labelTex, transparent: true });
      const label = new THREE.Sprite(labelMat);
      label.scale.set(1.5, 0.42, 1);
      label.position.set(x, colH + 0.62, z);
      label.userData = { baseY: colH + 0.62, phaseOffset: Math.random() * Math.PI * 2 };
      scene.add(label);

      disc.userData = { zone: zone.key };
      col.userData = { zone: zone.key };
    });

    pinMeshes.current = pins;
    pinToZone.current = pinMap;

    // =========================================================
    // LIGHTING
    // =========================================================
    // Ambient — very dim deep blue space light
    const ambient = new THREE.AmbientLight(0x0a1628, 1.2);
    scene.add(ambient);

    // Primary sun directional — warm white top-right
    const sun = new THREE.DirectionalLight(0xffffff, 1.1);
    sun.position.set(6, 12, 6);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    sun.shadow.camera.far = 30;
    scene.add(sun);

    // Rim fill — cool blue from opposite side
    const rimLight = new THREE.DirectionalLight(0x2563eb, 0.25);
    rimLight.position.set(-6, 4, -6);
    scene.add(rimLight);

    // Emerald accent point (from below center)
    const emeraldPt = new THREE.PointLight(0x059669, 0.6, 12);
    emeraldPt.position.set(0, -1, 0);
    scene.add(emeraldPt);

    // =========================================================
    // STARS (background particle system)
    // =========================================================
    const starCount = 600;
    const starPositions = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount; i++) {
      starPositions[i * 3 + 0] = (Math.random() - 0.5) * 80;
      starPositions[i * 3 + 1] = Math.random() * 25 + 2;
      starPositions[i * 3 + 2] = (Math.random() - 0.5) * 80;
    }
    const starGeo = new THREE.BufferGeometry();
    starGeo.setAttribute("position", new THREE.BufferAttribute(starPositions, 3));
    const starMat = new THREE.PointsMaterial({ color: 0x475569, size: 0.05, transparent: true, opacity: 0.3 });
    scene.add(new THREE.Points(starGeo, starMat));

    // =========================================================
    // RAYCASTER INTERACTION
    // =========================================================
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const onClick = (e: MouseEvent) => {
      const bounds = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - bounds.left) / bounds.width) * 2 - 1;
      mouse.y = -((e.clientY - bounds.top) / bounds.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const hits = raycaster.intersectObjects(pinMeshes.current);
      if (hits.length > 0) {
        const key = pinToZone.current.get(hits[0].object as THREE.Mesh);
        if (key) onSelectZone(key);
      }
    };

    const onMouseMove = (e: MouseEvent) => {
      const bounds = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - bounds.left) / bounds.width) * 2 - 1;
      mouse.y = -((e.clientY - bounds.top) / bounds.height) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const hits = raycaster.intersectObjects(pinMeshes.current);
      renderer.domElement.style.cursor = hits.length > 0 ? "pointer" : "grab";
    };

    renderer.domElement.addEventListener("click", onClick);
    renderer.domElement.addEventListener("mousemove", onMouseMove);

    // =========================================================
    // RESIZE OBSERVER
    // =========================================================
    const resizer = new ResizeObserver(entries => {
      const entry = entries[0];
      if (!entry) return;
      const { width: w, height: h } = entry.contentRect;
      if (w > 0 && h > 0) {
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
      }
    });
    resizer.observe(el);

    // =========================================================
    // ANIMATION LOOP
    // =========================================================
    let frameId: number;
    let lastTime = performance.now();
    let elapsed = 0;

    const animate = () => {
      frameId = requestAnimationFrame(animate);

      const now = performance.now();
      const delta = (now - lastTime) / 1000;
      lastTime = now;
      elapsed += delta;

      // Animate ring pulses
      scene.children.forEach(obj => {
        if (obj instanceof THREE.Mesh && obj.userData?.type === "ring") {
          obj.userData.t += delta * 1.6;
          const s = 1.0 + (obj.userData.t % 1.0) * 1.8;
          obj.scale.set(s, s, 1);
          (obj.material as THREE.MeshBasicMaterial).opacity =
            0.7 * (1 - (obj.userData.t % 1.0));
        }
      });

      // Animate label sprites float
      scene.children.forEach(obj => {
        if (obj instanceof THREE.Sprite && obj.userData?.baseY !== undefined) {
          obj.position.y =
            obj.userData.baseY + 0.07 * Math.sin(elapsed * 2.2 + obj.userData.phaseOffset);
        }
      });

      // Gentle horizontal sway on whole scene
      scene.rotation.y = 0.035 * Math.sin(elapsed * 0.12);

      controls.update();
      renderer.render(scene, camera);
    };

    animate();

    return () => {
      cancelAnimationFrame(frameId);
      resizer.disconnect();
      renderer.domElement.removeEventListener("click", onClick);
      renderer.domElement.removeEventListener("mousemove", onMouseMove);
      renderer.domElement.remove();
      scene.clear();
      renderer.dispose();
    };
  }, [zones, onSelectZone]);

  return (
    <div className="relative w-full h-full flex items-center justify-center overflow-hidden">
      {/* WebGL canvas */}
      <div
        ref={containerRef}
        className="w-full h-full"
        style={{ minHeight: 380 }}
      />

      {/* HUD overlay — top */}
      <div className="absolute top-3 left-3 right-3 flex items-center justify-between pointer-events-none z-20">
        <div className="glass-card px-3 py-1.5 flex items-center gap-2">
          <span className="dot-pulse emerald" />
          <span className="section-label" style={{ color: "var(--emerald-400)" }}>
            Live Region Map
          </span>
        </div>
        <div className="glass-card px-3 py-1.5">
          <span className="section-label">
            {zones.length} zones monitored
          </span>
        </div>
      </div>

      {/* HUD — bottom legend */}
      <div className="absolute bottom-3 left-0 right-0 flex justify-center pointer-events-none z-20">
        <div
          className="glass-card px-4 py-2 flex items-center gap-5"
          style={{ fontSize: 9, fontFamily: "monospace", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}
        >
          <span className="flex items-center gap-1.5">
            <span style={{ width: 8, height: 8, borderRadius: 2, background: "#dc2626", display: "inline-block" }} />
            Critical Alert
          </span>
          <span className="flex items-center gap-1.5">
            <span style={{ width: 8, height: 8, borderRadius: 2, background: "#059669", display: "inline-block" }} />
            Stable Zone
          </span>
          <span>Drag • Scroll Zoom • Click to Audit</span>
        </div>
      </div>
    </div>
  );
}

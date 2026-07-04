import { useMemo } from 'react'
import {
  MeshStandardMaterial,
  Shape,
  Path,
  ShapeGeometry,
} from 'three'
import type { ThreeEvent } from '@react-three/fiber'
import {
  FLOOR_HEIGHT_M,
  wallPolylines,
  type WallRect,
} from '../../data/floorPlan'
import { getFloorOuterAndHolePolygons } from '../../utils/floorPolygon'
import { pointInAnyRect } from '../../utils/rectUtils'

export function FloorPolygonMesh({
  yOffset,
  material,
  onDoubleClick,
  onClick,
  onPointerDown,
  onPointerMove,
}: {
  yOffset: number
  material: MeshStandardMaterial
  onDoubleClick?: (event: ThreeEvent<MouseEvent>) => void
  onClick?: (event: ThreeEvent<MouseEvent>) => void
  onPointerDown?: (event: ThreeEvent<PointerEvent>) => void
  onPointerMove?: (event: ThreeEvent<PointerEvent>) => void
}) {
  const geometry = useMemo(() => {
    const { outer, holes } = getFloorOuterAndHolePolygons(wallPolylines)
    if (outer.length < 3) return null

    const shape = new Shape()
    shape.moveTo(outer[0][0], outer[0][1])
    for (let i = 1; i < outer.length; i++) {
      shape.lineTo(outer[i][0], outer[i][1])
    }
    shape.closePath()

    for (const hole of holes) {
      if (hole.length < 3) continue
      const p = new Path()
      p.moveTo(hole[0][0], hole[0][1])
      for (let i = 1; i < hole.length; i++) {
        p.lineTo(hole[i][0], hole[i][1])
      }
      p.closePath()
      shape.holes.push(p)
    }

    const sg = new ShapeGeometry(shape)
    const pos = sg.attributes.position
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i)
      const z = pos.getY(i) // Shape's Y is our world Z
      pos.setXYZ(i, x, 0, z)
    }
    pos.needsUpdate = true
    sg.computeVertexNormals()
    return sg
  }, [])

  if (!geometry) return null

  return (
    <mesh
      geometry={geometry}
      material={material}
      position={[0, yOffset, 0]}
      rotation={[0, 0, 0]}
      frustumCulled={false}
      onDoubleClick={onDoubleClick}
      onClick={onClick}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
    />
  )
}

export function BookstoreLights({ floorRenderRects }: { floorRenderRects: WallRect[] }) {
  const positions = useMemo(() => {
    let minX = Infinity, maxX = -Infinity
    let minZ = Infinity, maxZ = -Infinity
    for (const r of floorRenderRects) {
      minX = Math.min(minX, r.cx - r.w / 2)
      maxX = Math.max(maxX, r.cx + r.w / 2)
      minZ = Math.min(minZ, r.cz - r.d / 2)
      maxZ = Math.max(maxZ, r.cz + r.d / 2)
    }

    const result: [number, number, number][] = []
    const spacing = 10
    const y = FLOOR_HEIGHT_M - 0.5
    for (let x = minX + spacing / 2; x <= maxX; x += spacing) {
      for (let z = minZ + spacing / 2; z <= maxZ; z += spacing) {
        if (pointInAnyRect(floorRenderRects, x, z)) result.push([x, y, z])
      }
    }
    return result
  }, [floorRenderRects])

  return (
    <>
      {positions.map((pos, i) => (
        <pointLight
          key={i}
          position={pos}
          color="#FFE0B2"
          intensity={2.5}
          distance={14}
          decay={2}
        />
      ))}
    </>
  )
}

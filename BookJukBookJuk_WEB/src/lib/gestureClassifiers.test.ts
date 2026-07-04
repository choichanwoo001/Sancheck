import { describe, expect, it } from 'vitest'
import {
  CLOSEST_HAND_MIN_BOX_AREA,
  classifyOneHandGesture,
  handLandmarkBoxArea,
  pickClosestHandLandmarks,
  type HandLandmark,
} from './gestureClassifiers'

function pt(x: number, y: number): HandLandmark {
  return { x, y }
}

function fullLm(
  wrist: HandLandmark,
  thumbTip: HandLandmark,
  indexTip: HandLandmark,
  middleTip: HandLandmark,
  ringTip: HandLandmark,
  pinkyTip: HandLandmark,
  joints: Partial<Record<'thumbIp' | 'indexPip' | 'middlePip' | 'ringPip' | 'pinkyPip', HandLandmark>> = {},
): HandLandmark[] {
  const pts: HandLandmark[] = Array.from({ length: 21 }, () => pt(wrist.x, wrist.y))
  pts[0] = wrist
  pts[3] = joints.thumbIp ?? pt(wrist.x + 0.02, wrist.y + 0.02)
  pts[4] = thumbTip
  pts[5] = pt(wrist.x + 0.04, wrist.y)
  pts[6] = joints.indexPip ?? pt(wrist.x + 0.04, wrist.y - 0.04)
  pts[8] = indexTip
  pts[9] = pt(wrist.x + 0.05, wrist.y)
  pts[10] = joints.middlePip ?? pt(wrist.x + 0.05, wrist.y - 0.04)
  pts[12] = middleTip
  pts[13] = pt(wrist.x + 0.06, wrist.y)
  pts[14] = joints.ringPip ?? pt(wrist.x + 0.06, wrist.y - 0.03)
  pts[16] = ringTip
  pts[17] = pt(wrist.x + 0.07, wrist.y)
  pts[18] = joints.pinkyPip ?? pt(wrist.x + 0.07, wrist.y - 0.02)
  pts[20] = pinkyTip
  return pts
}

describe('classifyOneHandGesture', () => {
  it('classifies open palm as stop', () => {
    const w = pt(0.5, 0.7)
    const far = pt(0.5, 0.2)
    const lm = fullLm(w, far, far, far, far, far)
    expect(classifyOneHandGesture(lm)).toBe('stop')
  })

  it('classifies fist as follow_me', () => {
    const w = pt(0.5, 0.7)
    const tip = pt(0.502, 0.698)
    const joint = pt(0.5, 0.45)
    const lm = fullLm(w, tip, tip, tip, tip, tip, {
      thumbIp: joint,
      indexPip: joint,
      middlePip: joint,
      ringPip: joint,
      pinkyPip: joint,
    })
    expect(classifyOneHandGesture(lm)).toBe('follow_me')
  })

  it('classifies L-shape as lead_again', () => {
    const w = pt(0.5, 0.7)
    const lm = fullLm(
      w,
      pt(0.42, 0.68),
      pt(0.5, 0.35),
      pt(0.52, 0.68),
      pt(0.54, 0.68),
      pt(0.56, 0.68),
      {
        thumbIp: pt(0.46, 0.68),
        indexPip: pt(0.5, 0.55),
        middlePip: pt(0.52, 0.66),
        ringPip: pt(0.54, 0.66),
        pinkyPip: pt(0.56, 0.66),
      },
    )
    expect(classifyOneHandGesture(lm)).toBe('lead_again')
  })

  it('picks only the closest visible hand by landmark box area', () => {
    const farHand = fullLm(
      pt(0.5, 0.55),
      pt(0.5, 0.51),
      pt(0.5, 0.5),
      pt(0.51, 0.5),
      pt(0.52, 0.5),
      pt(0.53, 0.5),
    )
    const closeHand = fullLm(
      pt(0.5, 0.8),
      pt(0.25, 0.25),
      pt(0.45, 0.15),
      pt(0.55, 0.12),
      pt(0.65, 0.18),
      pt(0.75, 0.22),
    )

    expect(handLandmarkBoxArea(closeHand)).toBeGreaterThan(handLandmarkBoxArea(farHand))
    expect(pickClosestHandLandmarks([farHand, closeHand])).toBe(closeHand)
  })

  it('ignores hands that are too small in the camera frame', () => {
    const tinyHand = fullLm(
      pt(0.5, 0.5),
      pt(0.505, 0.495),
      pt(0.51, 0.49),
      pt(0.515, 0.49),
      pt(0.52, 0.495),
      pt(0.525, 0.5),
      {
        thumbIp: pt(0.504, 0.498),
        indexPip: pt(0.508, 0.497),
        middlePip: pt(0.512, 0.497),
        ringPip: pt(0.516, 0.498),
        pinkyPip: pt(0.52, 0.499),
      },
    )

    expect(handLandmarkBoxArea(tinyHand)).toBeLessThan(CLOSEST_HAND_MIN_BOX_AREA)
    expect(pickClosestHandLandmarks([tinyHand])).toBeNull()
  })
})

// Hockey-themed workout signals, synthesized with Web Audio -- no audio
// files to license, download or cache, and every sound can be scheduled at
// an exact time on the AudioContext clock (what the lock-screen player
// relies on: the audio thread plays them on time even while iOS has frozen
// the page). Works on any BaseAudioContext, so the same code renders the
// preview WAVs offline.
//
//   stickTap  -- countdown tick (3-2-1): a stick tapped on the ice
//   buzzer    -- work over: the arena's end-of-shift buzzer
//   whistle   -- rest over, go: the referee's face-off whistle
//   goalHorn  -- exercise done: the goal horn

export type Track = (node: AudioScheduledSourceNode) => void

const noiseBuffers = new WeakMap<BaseAudioContext, AudioBuffer>()

function noiseBuffer(ctx: BaseAudioContext): AudioBuffer {
  let buffer = noiseBuffers.get(ctx)
  if (buffer === undefined) {
    buffer = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate)
    const data = buffer.getChannelData(0)
    for (let i = 0; i < data.length; i += 1) {
      data[i] = Math.random() * 2 - 1
    }
    noiseBuffers.set(ctx, buffer)
  }
  return buffer
}

function envelope(ctx: BaseAudioContext, at: number, peak: number, attack: number, hold: number, release: number): GainNode {
  const gain = ctx.createGain()
  gain.gain.setValueAtTime(0.0001, at)
  gain.gain.exponentialRampToValueAtTime(peak, at + attack)
  gain.gain.setValueAtTime(peak, at + attack + hold)
  gain.gain.exponentialRampToValueAtTime(0.0001, at + attack + hold + release)
  return gain
}

// Short wooden "tock": a noise click through a band-pass plus a low thump.
export function stickTap(ctx: BaseAudioContext, at: number, track: Track): void {
  const noise = ctx.createBufferSource()
  noise.buffer = noiseBuffer(ctx)
  const band = ctx.createBiquadFilter()
  band.type = 'bandpass'
  band.frequency.value = 1900
  band.Q.value = 3
  const click = envelope(ctx, at, 0.9, 0.002, 0.005, 0.06)
  noise.connect(band).connect(click).connect(ctx.destination)
  noise.start(at, Math.random() * 0.5)
  noise.stop(at + 0.1)
  track(noise)

  const thump = ctx.createOscillator()
  thump.frequency.setValueAtTime(220, at)
  thump.frequency.exponentialRampToValueAtTime(110, at + 0.06)
  const body = envelope(ctx, at, 0.35, 0.002, 0.01, 0.07)
  thump.connect(body).connect(ctx.destination)
  thump.start(at)
  thump.stop(at + 0.1)
  track(thump)
}

// Arena buzzer: two slightly detuned square waves, softened, flat ~0.9 s.
export function buzzer(ctx: BaseAudioContext, at: number, track: Track): void {
  const lowpass = ctx.createBiquadFilter()
  lowpass.type = 'lowpass'
  lowpass.frequency.value = 1800
  const gain = envelope(ctx, at, 0.16, 0.01, 0.8, 0.08)
  lowpass.connect(gain).connect(ctx.destination)
  for (const frequency of [370, 376]) {
    const oscillator = ctx.createOscillator()
    oscillator.type = 'square'
    oscillator.frequency.value = frequency
    oscillator.connect(lowpass)
    oscillator.start(at)
    oscillator.stop(at + 0.95)
    track(oscillator)
  }
}

// Pea whistle: a ~3 kHz tone with the fast trill of the pea (frequency
// modulation around 30 Hz) plus a breath of high noise. Two short blasts.
export function whistle(ctx: BaseAudioContext, at: number, track: Track): void {
  const blasts: [number, number][] = [
    [0, 0.16],
    [0.24, 0.42],
  ]
  for (const [offset, length] of blasts) {
    const start = at + offset
    const tone = ctx.createOscillator()
    tone.frequency.value = 3050
    const trill = ctx.createOscillator()
    trill.frequency.value = 32
    const trillDepth = ctx.createGain()
    trillDepth.gain.value = 180
    trill.connect(trillDepth).connect(tone.frequency)
    const toneGain = envelope(ctx, start, 0.22, 0.015, length - 0.05, 0.04)
    tone.connect(toneGain).connect(ctx.destination)

    const breath = ctx.createBufferSource()
    breath.buffer = noiseBuffer(ctx)
    const high = ctx.createBiquadFilter()
    high.type = 'bandpass'
    high.frequency.value = 3200
    high.Q.value = 1.5
    const breathGain = envelope(ctx, start, 0.05, 0.015, length - 0.05, 0.04)
    breath.connect(high).connect(breathGain).connect(ctx.destination)

    for (const node of [tone, trill, breath]) {
      node.start(start)
      node.stop(start + length + 0.02)
      track(node)
    }
  }
}

// Goal horn: a low brassy chord of sawtooths behind a low-pass, swelling in
// and holding ~1.8 s with a slight wobble.
export function goalHorn(ctx: BaseAudioContext, at: number, track: Track): void {
  const lowpass = ctx.createBiquadFilter()
  lowpass.type = 'lowpass'
  lowpass.frequency.value = 900
  lowpass.Q.value = 0.8
  const gain = envelope(ctx, at, 0.2, 0.12, 1.5, 0.35)
  lowpass.connect(gain).connect(ctx.destination)
  const wobble = ctx.createOscillator()
  wobble.frequency.value = 5
  const wobbleDepth = ctx.createGain()
  wobbleDepth.gain.value = 2.5
  wobble.connect(wobbleDepth)
  wobble.start(at)
  wobble.stop(at + 2.1)
  track(wobble)
  for (const frequency of [146.8, 185, 220]) {
    const oscillator = ctx.createOscillator()
    oscillator.type = 'sawtooth'
    oscillator.frequency.value = frequency
    wobbleDepth.connect(oscillator.frequency)
    oscillator.connect(lowpass)
    oscillator.start(at)
    oscillator.stop(at + 2.1)
    track(oscillator)
  }
}

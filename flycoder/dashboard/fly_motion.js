/**
 * Neural-to-motion mapping for the 3D embodied visualization.
 *
 * REAL: sensory_norm / descending_norm / control come from FlyCoder
 * (encoder drive and descending spike means). Destinations are selector results.
 *
 * EXPERIMENTAL: joint angles, damping targets, and tiny idle motion.
 * This is not Drosophila biomechanics.
 */
(function (global) {
  function clamp(v, a, b) {
    return Math.max(a, Math.min(b, v));
  }

  function n(obj, key) {
    const v = obj && obj[key];
    return Number.isFinite(v) ? v : 0;
  }

  /**
   * @param {object} state  latest FlyCoder snapshot
   * @param {number} t      seconds, for idle only
   * @returns {object} pose targets in radians / meters
   */
  function computeFlyPose(state, t) {
    const sn = state.sensory_norm || {};
    const dn = state.descending_norm || {};
    const ctrl = state.control || {};
    const env = state.env || {};
    const running = !!(state.running && !state.finished);

    const dnaL = n(dn, "dna02L");
    const dnaR = n(dn, "dna02R");
    const steer = clamp(n(ctrl, "steer") || (dnaR - dnaL), -1, 1);
    const commit = n(dn, "dnp01") * 0.55 + n(dn, "dng100") * 0.45;
    const mdn = n(dn, "mdn");
    const lcL = n(sn, "lc10aL");
    const lcR = n(sn, "lc10aR");
    const pitchIn = n(sn, "lplc1R") - n(sn, "lplc1L");
    const loom = Math.max(n(sn, "lc4"), n(sn, "lplc2"), n(sn, "error"));

    const idle = running ? 1 : 0.28;
    const idleLeg = Math.sin(t * 2.2) * 0.03 * idle;
    const idleAnt = Math.sin(t * 3.1) * 0.08 * idle;
    const breathe = Math.sin(t * 1.4) * 0.02 * idle;
    const wingIdle = Math.sin(t * 5.2) * 0.04 * idle;

    const yaw = steer * 0.28;
    const headYaw = clamp(steer * 0.32 + (lcR - lcL) * 0.4, -0.5, 0.5);
    const headPitch = clamp(pitchIn * 0.3 + commit * 0.18 - mdn * 0.12, -0.35, 0.4);
    const abdomen = breathe - mdn * 0.16 + loom * 0.04;
    const x = -mdn * 0.16;
    const z = commit * 0.04;

    const lift = 0.22 + (running ? 0.08 : 0) + loom * 0.1;
    const wingL = -0.22 + lift - Math.max(0, -steer) * 0.18 + wingIdle;
    const wingR = 0.22 - lift + Math.max(0, steer) * 0.18 - wingIdle;
    const wingReachL = 0.12 + Math.max(0, -steer) * 0.12;
    const wingReachR = 0.12 + Math.max(0, steer) * 0.12;

    const frontRetract = mdn * 0.45 - commit * 0.25;
    const rearExtend = mdn * 0.4;
    const legs = {
      LF: { yaw: 0.55 + steer * 0.15, lift: 0.15 + frontRetract + idleLeg, bend: 0.7 + frontRetract },
      RF: { yaw: -0.55 + steer * 0.15, lift: 0.15 + frontRetract - idleLeg, bend: 0.7 + frontRetract },
      LM: { yaw: 0.15 + steer * 0.12, lift: 0.08 + idleLeg * 0.5, bend: 0.55 },
      RM: { yaw: -0.15 + steer * 0.12, lift: 0.08 - idleLeg * 0.5, bend: 0.55 },
      LR: { yaw: -0.45 + steer * 0.1, lift: 0.05 - rearExtend, bend: 0.8 - rearExtend },
      RR: { yaw: 0.45 + steer * 0.1, lift: 0.05 - rearExtend, bend: 0.8 - rearExtend },
    };

    const vw = env.viewport_width || 1920;
    const vh = env.viewport_height || 1080;
    const hx = (env.horizontal_error || 0) / (vw * 0.5);
    const hy = (env.vertical_error || 0) / (vh * 0.5);

    let mode = (ctrl.mode || "SCANNING");
    if (!running && state.finished) mode = "EXPERIMENT COMPLETE";

    return {
      yaw,
      pitch: loom * 0.05,
      roll: steer * -0.08,
      x,
      z,
      headYaw,
      headPitch,
      abdomen,
      wingL,
      wingR,
      wingReachL,
      wingReachR,
      wingAmp: lift,
      antennaL: -0.35 + idleAnt - lcL * 0.2,
      antennaR: 0.35 - idleAnt + lcR * 0.2,
      legs,
      commit,
      mdn,
      loom,
      steer,
      selected: (state.selector && state.selector.index) || state.cursor || 0,
      target: { x: clamp(hx, -1, 1) * 1.15, y: clamp(-hy, -1, 1) * 0.7, z: 0.9 },
      eyeL: lcL,
      eyeR: lcR,
      mode,
      running,
      paused: !state.running && !state.finished,
    };
  }

  global.FlyMotion = { computeFlyPose };
})(window);

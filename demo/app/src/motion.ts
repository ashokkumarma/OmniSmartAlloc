import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);
gsap.defaults({ ease: "power3.out", duration: 0.4 });

/** True when the user asked the OS to reduce motion. Every animation checks this. */
export const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Short entrance for a view's top-level blocks. */
export function enter(targets: gsap.TweenTarget, opts: { y?: number; stagger?: number; delay?: number } = {}) {
  if (reducedMotion()) return;
  gsap.from(targets, { autoAlpha: 0, y: opts.y ?? 10, duration: 0.42, stagger: opts.stagger ?? 0.05, delay: opts.delay ?? 0, clearProps: "transform,opacity,visibility" });
}

/** Count a number up from its previous value; writes formatted text into el. */
export function countTo(el: HTMLElement, from: number, to: number, format: (n: number) => string): gsap.core.Tween | undefined {
  if (reducedMotion() || from === to) {
    el.textContent = format(to);
    return undefined;
  }
  const obj = { v: from };
  return gsap.to(obj, { v: to, duration: 0.9, ease: "power2.out", onUpdate: () => { el.textContent = format(Math.round(obj.v)); } });
}

export { gsap, useGSAP };

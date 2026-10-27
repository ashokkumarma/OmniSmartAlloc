import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);
gsap.defaults({ ease: "power2.out", duration: 0.2 });

/** True when the user asked the OS to reduce motion. Every animation checks this. */
export const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** A view's blocks fade in when the view opens (a change of screen). Opacity only, 200 ms. */
export function enter(targets: gsap.TweenTarget) {
  if (reducedMotion()) return;
  gsap.from(targets, { opacity: 0, duration: 0.2, clearProps: "opacity" });
}

export { gsap, useGSAP };

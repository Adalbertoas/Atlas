import { useEffect, useRef } from "react";
import type { AtlasInteractionController } from "../interaction/AtlasInteractionController.ts";
import { useNeuralLive } from "./useNeuralCore.ts";

const BONES: readonly (readonly [number, number])[] = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [0, 5], [5, 6], [6, 7], [7, 8],
  [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16],
  [13, 17], [17, 18], [18, 19], [19, 20], [0, 17],
];

const WIDTH = 240;
const HEIGHT = 180;

/** Vista de depuración opcional: landmarks suavizados y, solo si se pide, la
    imagen de la cámara. Se dibuja en local y no se guarda nada. */
export function HandDebugOverlay({ runtime, showCamera }: { runtime: AtlasInteractionController; showCamera: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const live = useNeuralLive(runtime);

  useEffect(() => {
    const context = canvasRef.current?.getContext("2d");
    if (!context) return;
    let frame = 0;
    const draw = () => {
      frame = requestAnimationFrame(draw);
      const { hands, video } = runtime.debug;
      context.fillStyle = "#020b14";
      context.fillRect(0, 0, WIDTH, HEIGHT);
      if (showCamera && video && video.readyState >= 2) {
        context.save();
        context.globalAlpha = 0.55;
        // Reflejada, igual que los landmarks.
        context.translate(WIDTH, 0);
        context.scale(-1, 1);
        context.drawImage(video, 0, 0, WIDTH, HEIGHT);
        context.restore();
      }
      context.lineWidth = 1.5;
      for (const hand of hands) {
        context.strokeStyle = "rgba(82,223,255,.8)";
        context.beginPath();
        for (const [from, to] of BONES) {
          context.moveTo(hand.landmarks[from].x * WIDTH, hand.landmarks[from].y * HEIGHT);
          context.lineTo(hand.landmarks[to].x * WIDTH, hand.landmarks[to].y * HEIGHT);
        }
        context.stroke();
        context.fillStyle = "#dffbff";
        for (const point of hand.landmarks) context.fillRect(point.x * WIDTH - 1.5, point.y * HEIGHT - 1.5, 3, 3);
      }
    };
    draw();
    return () => cancelAnimationFrame(frame);
  }, [runtime, showCamera]);

  return <div className="neural-debug">
    <canvas ref={canvasRef} width={WIDTH} height={HEIGHT} />
    <small>{live.handCount} mano(s) · {live.inferenceMs ?? "--"} ms{live.activeGestures.length ? ` · ${live.activeGestures.join(", ")}` : ""}</small>
  </div>;
}

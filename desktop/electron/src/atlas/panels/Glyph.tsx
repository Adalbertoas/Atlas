// Iconos de línea de los paneles (mismo trazo que los del menú lateral).
import type { ReactNode } from "react";

const paths: Record<string, ReactNode> = {
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5" /></>,
  moon: <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />,
  partly: <><path d="M8 3v1.5M3.5 8H2M4.8 4.8l1 1M13.5 4.8l-1 1" /><path d="M5.5 11a3.5 3.5 0 0 1 6.6-2" /><path d="M8 20h9a4 4 0 0 0 0-8 5 5 0 0 0-9.6 1.5A3.3 3.3 0 0 0 8 20Z" /></>,
  cloud: <path d="M7 19h10a4.5 4.5 0 0 0 .4-9A6 6 0 0 0 6 11.5 3.8 3.8 0 0 0 7 19Z" />,
  fog: <><path d="M7 14h10a4 4 0 0 0 .4-8A6 6 0 0 0 6 7.5 3.3 3.3 0 0 0 7 14Z" /><path d="M4 18h16M7 21h10" /></>,
  drizzle: <><path d="M7 14h10a4 4 0 0 0 .4-8A6 6 0 0 0 6 7.5 3.3 3.3 0 0 0 7 14Z" /><path d="M9 17v1M13 18v1M17 17v1" /></>,
  rain: <><path d="M7 14h10a4 4 0 0 0 .4-8A6 6 0 0 0 6 7.5 3.3 3.3 0 0 0 7 14Z" /><path d="m9 17-1 3M13 17l-1 3M17 17l-1 3" /></>,
  snow: <><path d="M7 14h10a4 4 0 0 0 .4-8A6 6 0 0 0 6 7.5 3.3 3.3 0 0 0 7 14Z" /><path d="M9 18h.01M13 20h.01M17 18h.01M11 22h.01" /></>,
  storm: <><path d="M7 14h10a4 4 0 0 0 .4-8A6 6 0 0 0 6 7.5 3.3 3.3 0 0 0 7 14Z" /><path d="m13 14-3 4h4l-3 4" /></>,
  drop: <path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11Z" />,
  wind: <path d="M3 9h11a3 3 0 1 0-3-3M3 15h15a3 3 0 1 1-3 3M3 12h7" />,
  trash: <><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  search: <><circle cx="11" cy="11" r="6" /><path d="m20 20-4.2-4.2" /></>,
  bell: <path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 22h4" />,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  news: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M7 8h10M7 12h10M7 16h6" /></>,
  calc: <><rect x="5" y="2" width="14" height="20" rx="2" /><path d="M8 6h8M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h.01M8 19h8" /></>,
  coin: <><circle cx="12" cy="12" r="9" /><path d="M15 9a3 3 0 0 0-3-1.5c-1.7 0-3 .9-3 2.2 0 3 6 1.6 6 4.6 0 1.3-1.3 2.2-3 2.2A3.2 3.2 0 0 1 9 15M12 6v1.5M12 16.5V18" /></>,
  key: <><circle cx="8" cy="15" r="4" /><path d="m11 12 9-9M17 6l3 3M15 8l2 2" /></>,
  globe: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></>,
  volume: <><path d="M4 9v6h4l5 4V5L8 9Z" /><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11" /></>,
  lock: <><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></>,
  briefing: <><path d="M12 3v2M5 7l1.5 1.5M19 7l-1.5 1.5M3 14h2M19 14h2" /><path d="M8 18a4 4 0 1 1 8 0M4 21h16" /></>,
  camera: <><path d="M4 8h3l2-3h6l2 3h3v11H4Z" /><circle cx="12" cy="13" r="3.5" /></>,
  music: <><path d="M9 18V5l11-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="17" cy="16" r="3" /></>,
  brain: <><path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 6 1V5a2 2 0 0 0-3-1Z" /><path d="M15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-6 1" /></>,
  check: <path d="m5 12 4 4L19 6" />,
  x: <path d="M6 6l12 12M18 6 6 18" />,
  sparkle: <path d="m12 2 1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8Z" />,
  user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  alert: <><path d="M12 3 2 20h20Z" /><path d="M12 10v4M12 17h.01" /></>,
  refresh: <><path d="M20 11a8 8 0 0 0-14.9-3M4 4v4h4M4 13a8 8 0 0 0 14.9 3M20 20v-4h-4" /></>,
  image: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="8.5" cy="9.5" r="1.5" /><path d="m21 15-5-5L5 20" /></>,
  brush: <><path d="M18.4 2.6a2 2 0 0 1 2.9 2.9L12 14.8 9.2 12Z" /><path d="M9.2 12C6 12 4.5 14 4.5 16c0 1.4-.8 2.6-2 3 1.2 1.4 3.2 2 5 2 3.3 0 4.5-2.3 4.5-4.5" /></>,
  pen: <><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></>,
  vector: <><path d="M5 19 12 5l7 14" /><rect x="10" y="3" width="4" height="4" /><rect x="3" y="17" width="4" height="4" /><rect x="17" y="17" width="4" height="4" /></>,
  download: <path d="M12 3v12M7 10l5 5 5-5M4 21h16" />,
  folder: <path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />,
  expand: <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />,
  bulb: <><path d="M9 18h6M10 21h4" /><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3Z" /></>,
  quote: <path d="M7 7h4v4c0 3-2 5-4 6M15 7h4v4c0 3-2 5-4 6" />,
  film: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4" /></>,
};

export function Glyph({ name, size = 18, className }: { name: string; size?: number; className?: string }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name] ?? paths.sparkle}
    </svg>
  );
}

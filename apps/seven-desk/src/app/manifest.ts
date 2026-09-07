import type { MetadataRoute } from "next";
import { DESK_THEME_COLOR } from "@/lib/desk-theme";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Seven Desk",
    short_name: "Seven Desk",
    description:
      "Paper copy-trading across seven prop-firm accounts you operate, from one browser terminal.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: DESK_THEME_COLOR,
    theme_color: DESK_THEME_COLOR,
    orientation: "any",
    icons: [
      {
        src: "/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}

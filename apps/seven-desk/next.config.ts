import type { NextConfig } from "next";

const extraOrigins = (process.env.SEVEN_DESK_DEV_ORIGINS ?? "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);

const nextConfig: NextConfig = {
  agentRules: false,
  // next dev binds 0.0.0.0:3847; Tailscale IP / MagicDNS are not localhost.
  allowedDevOrigins: [
    "127.0.0.1",
    "localhost",
    "*.ts.net",
    "100.95.218.24",
    ...extraOrigins,
  ],
};

export default nextConfig;

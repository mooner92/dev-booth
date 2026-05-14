const isDev = process.env.NODE_ENV !== "production";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: true },
  ...(isDev && {
    async rewrites() {
      // Dev-only proxy. Production single-port mode serves /api/* same-origin
      // via the FastAPI process (when DASHBOARD_STATIC_DIR is set).
      return [
        { source: "/api/:path*", destination: "http://localhost:7001/api/:path*" },
        { source: "/ws/:path*", destination: "http://localhost:7001/ws/:path*" },
      ];
    },
  }),
};

export default nextConfig;

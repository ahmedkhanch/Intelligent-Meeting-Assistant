/** @type {import('next').NextConfig} */

// Proxy target for /api/* rewrites. Defaults to localhost for host dev; in Docker
// this is set to http://backend:8000 so the Next.js server can reach the FastAPI
// container over the compose network.
const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';

const nextConfig = {
  async rewrites() {
    return [
      {
        // Proxy /api/* to the FastAPI backend
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  basePath: '/dashboard',
  images: {
    unoptimized: true,
  },
  async rewrites() {
    return [
      { source: '/paper/:path*', destination: 'http://localhost:8000/paper/:path*' },
      { source: '/status', destination: 'http://localhost:8000/status' },
      { source: '/risk', destination: 'http://localhost:8000/risk' },
      { source: '/health', destination: 'http://localhost:8000/health' },
      { source: '/exchange/:path*', destination: 'http://localhost:8000/exchange/:path*' },
      { source: '/strategies/:path*', destination: 'http://localhost:8000/strategies/:path*' },
      { source: '/explore/:path*', destination: 'http://localhost:8000/explore/:path*' },
      { source: '/data/:path*', destination: 'http://localhost:8000/data/:path*' },
      { source: '/logs', destination: 'http://localhost:8000/logs' },
      { source: '/engine/:path*', destination: 'http://localhost:8000/engine/:path*' },
    ];
  },
};

module.exports = nextConfig;

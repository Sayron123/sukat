import type { NextConfig } from "next";

import packageJson from "./package.json";
import { securityHeaders } from "./security-headers";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  env: { NEXT_PUBLIC_APP_VERSION: packageJson.version },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders() }];
  },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;

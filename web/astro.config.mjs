// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';

// Static output, directory-format clean routes (/method → /method/index.html),
// served by Caddy on the box. React only hydrates the interactive islands
// (the agent chat + the MapLibre maps); everything else ships as static HTML.
export default defineConfig({
  site: 'https://riparian.emeraldleaf.dev',
  integrations: [react()],
  build: { format: 'directory' },
  devToolbar: { enabled: false },
});

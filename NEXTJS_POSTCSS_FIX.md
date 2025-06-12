# Fixing Tailwind CSS PostCSS plugin error in Next.js 15

If your Next.js 15 project fails to build with the following error:

```
Error: It looks like you're trying to use `tailwindcss` directly as a PostCSS plugin.
The PostCSS plugin has moved to a separate package, so to continue using Tailwind CSS with PostCSS you'll need to install `@tailwindcss/postcss` and update your PostCSS configuration.
```

follow these steps:

1. **Install the correct PostCSS plugin**

   ```bash
   npm install --save-dev @tailwindcss/postcss
   ```

   or with Yarn:

   ```bash
   yarn add --dev @tailwindcss/postcss
   ```

2. **Update `postcss.config.mjs`**

   Replace any reference to `require('tailwindcss')` with `require('@tailwindcss/postcss')`.

   Example `postcss.config.mjs`:

   ```js
   module.exports = {
     plugins: {
       '@tailwindcss/postcss': {},
       autoprefixer: {},
     },
   };
   ```

3. **Restart the development server**

   After updating the configuration and installing the plugin, restart your Next.js development server:

   ```bash
   npm run dev
   ```

This should resolve the build error and allow Turbopack to properly compile your Tailwind CSS styles.


/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bwssb: {
          blue: '#005b94',
          dark: '#0a192f',
          surface: '#112240',
          accent: '#00b4d8',
          warn: '#f59e0b',
          danger: '#ef4444',
          success: '#10b981',
        }
      }
    },
  },
  plugins: [],
}

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        serif: ['"Playfair Display"', 'Georgia', 'serif'],
        sans:  ['Outfit', 'system-ui', 'sans-serif'],
      },
      colors: {
        primary: {
          DEFAULT: '#c9a84c',
          dark:    '#a8893a',
          light:   '#e2b96a',
        },
        dark: {
          base:    '#07070b',
          DEFAULT: '#0d1117',
          card:    '#161b22',
          lighter: '#21262d',
        },
        gold: {
          DEFAULT: '#c9a84c',
          light:   '#e2b96a',
        },
        manga: {
          DEFAULT: '#6b9bd2',
        },
        comic: {
          DEFAULT: '#c07a5a',
        },
        book: {
          DEFAULT: '#7aa67a',
        },
      },
      animation: {
        'fade-in':  'fadeIn 0.3s ease-in',
        'slide-up': 'slideUp 0.3s ease-out',
        'shimmer':  'shimmer 1.8s linear infinite',
        'page-in':  'pageIn 0.2s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%':   { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)',    opacity: '1' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        pageIn: {
          '0%':   { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  safelist: [
    { pattern: /bg-(manga|comic|book)(\/\d+)?/ },
    { pattern: /text-(manga|comic|book)/ },
    { pattern: /border-(manga|comic|book)(\/\d+)?/ },
    { pattern: /from-(manga|comic|book)/ },
  ],
  plugins: [],
}

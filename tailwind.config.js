/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx}",
  ],
  theme: {
    extend: {
      animation: {
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'shimmer': 'shimmer 2s linear infinite',
        'liquid-pulse': 'liquid-pulse 2s infinite',
        'liquid-pulse-subtle': 'liquid-pulse-subtle 2s infinite',
      },
      keyframes: {
        'pulse-glow': {
          '0%, 100%': { boxShadow: '0 0 20px rgba(34, 197, 94, 0.5), inset 0 0 20px rgba(34, 197, 94, 0.2)' },
          '50%': { boxShadow: '0 0 40px rgba(34, 197, 94, 0.8), inset 0 0 30px rgba(34, 197, 94, 0.4)' },
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% center' },
          '100%': { backgroundPosition: '200% center' },
        },
        'liquid-pulse': {
          '0%': { 
            boxShadow: '0 0 0 0 rgba(52, 211, 153, 0.4), 0 8px 32px 0 rgba(0, 0, 0, 0.37)'
          },
          '70%': { 
            boxShadow: '0 0 0 20px rgba(52, 211, 153, 0), 0 8px 32px 0 rgba(52, 211, 153, 0.3)'
          },
          '100%': { 
            boxShadow: '0 0 0 0 rgba(52, 211, 153, 0), 0 8px 32px 0 rgba(0, 0, 0, 0.37)'
          },
        },
        'liquid-pulse-subtle': {
          '0%, 100%': { background: 'rgba(52, 211, 153, 0.1)' },
          '50%': { background: 'rgba(52, 211, 153, 0.15)' },
        },
      },
    },
  },
  plugins: [],
};

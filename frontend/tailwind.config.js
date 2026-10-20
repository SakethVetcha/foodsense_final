/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        cream: {
          50: '#FDFCF7',
          100: '#FAF7F0',
          200: '#F4EFE6',
          300: '#E8DEC8',
        },
        forest: {
          50: '#F0F7F4',
          100: '#D8ECE1',
          200: '#B2DAC3',
          500: '#40916C',
          600: '#2D6A4F',
          700: '#1B4332',
          800: '#081C15',
        },
        terracotta: {
          50: '#FDF3F0',
          100: '#FBE4DC',
          200: '#F5C4B3',
          500: '#E06D44',
          600: '#C85A32',
          700: '#A34320',
        },
      },
      fontFamily: {
        sans: ['Plus Jakarta Sans', 'Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
}

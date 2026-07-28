import defaultTheme from 'tailwindcss/defaultTheme'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eef7ff',
          100: '#d8edff',
          200: '#b9dfff',
          300: '#89ccff',
          400: '#51aeff',
          500: '#2890ff',
          600: '#0f72ff',
          700: '#0059ea',
          800: '#0049bd',
          900: '#004195',
          950: '#002a5a',
        },
        gray: {
          50: '#f6f7f9',
          100: '#eceef1',
          200: '#d5d9e0',
          300: '#b1b9c5',
          400: '#8793a4',
          500: '#687589',
          600: '#555f71',
          700: '#45505c',
          800: '#3a434e',
          900: '#343a44',
          950: '#23282e',
        },
        success: {
          light: '#d1fae5',
          DEFAULT: '#059669',
          dark: '#065f46',
        },
        error: {
          light: '#fee2e2',
          DEFAULT: '#dc2626',
          dark: '#991b1b',
        },
        warning: {
          light: '#fef3c7',
          DEFAULT: '#d97706',
          dark: '#92400e',
        },
        cancel: {
          light: '#f3f4f6',
          DEFAULT: '#6b7280',
          dark: '#374151',
        },
      },
      fontFamily: {
        sans: ['Inter', ...defaultTheme.fontFamily.sans],
      },
    },
  },
  plugins: [],
}

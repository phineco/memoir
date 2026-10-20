/** Tailwind 配置：家音 · 回忆录（暖纸色主题，老年友好） */
module.exports = {
  content: ['./templates/**/*.html', './static/*.js'],
  theme: {
    extend: {
      colors: {
        paper: '#faf7f0',
        ink: '#2c2c2c',
        accent: { DEFAULT: '#a5673f', dark: '#8a5533', soft: '#f3e9dc' },
        line: '#e5ddcf',
        leaf: { DEFAULT: '#2f7d2f', dark: '#256b26', soft: '#eef7ea' },
        danger: '#c0392b',
      },
      fontFamily: {
        serif: ['"Noto Serif SC"', '"Songti SC"', '"STSong"', 'serif'],
        sans: ['"PingFang SC"', '"Hiragino Sans GB"', '"Microsoft YaHei"', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 3px rgba(90, 70, 40, .08), 0 4px 14px rgba(90, 70, 40, .05)',
        lift: '0 4px 10px rgba(90, 70, 40, .12), 0 10px 28px rgba(90, 70, 40, .10)',
      },
    },
  },
  plugins: [],
};

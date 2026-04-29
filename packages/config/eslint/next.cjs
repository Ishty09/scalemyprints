/** @type {import('eslint').Linter.Config} */
module.exports = {
  extends: [
    'next/core-web-vitals',
    'prettier',
  ],
  plugins: ['@typescript-eslint', 'unused-imports'],
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 2022,
    sourceType: 'module',
    ecmaFeatures: {
      jsx: true,
    },
  },
  rules: {
    // Type safety
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/no-unused-vars': 'off',
    'unused-imports/no-unused-imports': 'error',
    'unused-imports/no-unused-vars': [
      'warn',
      {
        vars: 'all',
        varsIgnorePattern: '^_',
        args: 'after-used',
        argsIgnorePattern: '^_',
      },
    ],
    // React
    'react/react-in-jsx-scope': 'off',
    'react/prop-types': 'off',
    'react/no-unescaped-entities': 'off',
    // Next.js
    '@next/next/no-html-link-for-pages': 'off',
    // Code quality
    'prefer-const': 'error',
    'no-var': 'error',
    'no-console': ['warn', { allow: ['warn', 'error'] }],
  },
  settings: {
    react: { version: 'detect' },
  },
  ignorePatterns: ['node_modules', '.next', 'dist', 'build', 'coverage', '.turbo'],
}

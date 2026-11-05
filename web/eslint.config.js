// Lint configuration. Style is Prettier's job; this file holds rules
// about structure — chiefly the money boundary, which is a lint error
// rather than a review comment because review is one stretched person.
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'dev-dist', 'coverage', 'src/api/schema.d.ts', 'src/i18n/generated'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.strict],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      // [TC-7] Money never becomes a JS number. parseFloat/Number on a
      // money string is how a float sneaks in, so both are banned outside
      // the money module; the module itself has no use for them either.
      'no-restricted-globals': [
        'error',
        { name: 'parseFloat', message: 'Money is a string. Use core/money.ts.' },
      ],
      'no-restricted-properties': [
        'error',
        {
          object: 'Number',
          property: 'parseFloat',
          message: 'Money is a string. Use core/money.ts.',
        },
        { object: 'localStorage', property: 'clear', message: 'Clear only the keys you own.' },
      ],
    },
  },
  {
    // Tests own the whole of jsdom's storage and assert on fixtures they
    // just built, so a reset and a `!` on a known element are fine there.
    files: ['**/*.test.{ts,tsx}', 'src/test/**'],
    rules: {
      '@typescript-eslint/no-non-null-assertion': 'off',
      'no-restricted-properties': 'off',
    },
  },
  {
    files: ['scripts/**/*.mjs', '*.js'],
    extends: [js.configs.recommended],
    languageOptions: { ecmaVersion: 2022, globals: globals.node },
  },
)

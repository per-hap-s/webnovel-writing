import js from '@eslint/js'
import globals from 'globals'

const browserGlobals = {
    ...globals.browser,
    ...globals.node,
}

export default [
    {
        ignores: ['dist/**', 'node_modules/**'],
    },
    {
        files: ['src/**/*.{js,jsx}'],
        languageOptions: {
            ecmaVersion: 'latest',
            sourceType: 'module',
            parserOptions: {
                ecmaFeatures: {
                    jsx: true,
                },
            },
            globals: browserGlobals,
        },
        rules: {
            ...js.configs.recommended.rules,
            'no-unused-vars': 'off',
            'no-control-regex': 'off',
            'no-useless-escape': 'off',
        },
    },
]

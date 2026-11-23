import '@testing-library/jest-dom/vitest'
import { configure } from '@testing-library/react'

// How long findBy* and waitFor wait before failing. The library's default
// is one second, which a lazily loaded screen (lazyScreen) plus its first
// request can outlast on a busy CI runner, so a correct screen read as
// missing. A wait still ends as soon as its condition holds, so a passing
// test is no slower; only a test that is going to fail waits longer.
// Three seconds matches the one explicit wait that already needed it
// (noIdentifierLeaks.test.tsx) and stays under Vitest's five-second test
// timeout.
configure({ asyncUtilTimeout: 3000 })

import { describe, expect, it } from 'vitest'
import { pageWidth } from './pageWidth'

describe('pageWidth', () => {
  it.each([
    ['/today', 'full'],
    ['/students', 'full'],
    ['/batches/b1', 'full'],
    ['/verify', 'full'],
    ['/dues', 'full'],
    ['/my/e1', 'full'],
    ['/batches/new', 'form'],
    ['/students/new', 'form'],
    ['/batches/b1/edit', 'form'],
    ['/my/e1/pay', 'form'],
    ['/child/e1/pay', 'form'],
    ['/settings', 'form'],
    ['/more', 'reading'],
    ['/inbox', 'reading'],
    ['/inbox/n1', 'reading'],
    ['/seats/e1/fees', 'reading'],
    ['/child/e1/progress', 'reading'],
    ['/my/e1/exams/x1', 'reading'],
    ['/more/', 'reading'],
    ['/help', 'reading'],
    ['/help/new', 'form'],
    ['/help/t1', 'reading'],
  ])('%s is %s', (path, width) => {
    expect(pageWidth(path)).toBe(width)
  })
})

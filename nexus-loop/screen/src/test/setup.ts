import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => cleanup())

const dialogPrototype = typeof HTMLDialogElement === 'undefined' ? null : HTMLDialogElement.prototype
const originalShowModal = dialogPrototype?.showModal
const originalClose = dialogPrototype?.close

beforeAll(() => {
  if (!dialogPrototype) return
  dialogPrototype.showModal = function showModal() {
    this.setAttribute('open', '')
  }
  dialogPrototype.close = function close() {
    this.removeAttribute('open')
    this.dispatchEvent(new Event('close'))
  }
})

afterAll(() => {
  if (!dialogPrototype || !originalShowModal || !originalClose) return
  dialogPrototype.showModal = originalShowModal
  dialogPrototype.close = originalClose
})

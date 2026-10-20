// Recharts' ResponsiveContainer observes its box with ResizeObserver, which
// jsdom does not implement. A no-op observer is enough: the charts still mount
// and their accessible/text content is what the tests assert on.

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = globalThis.ResizeObserver || ResizeObserverStub

// jsdom defines window.scrollTo but throws "Not implemented". The planner calls
// it to jump to the top of the dashboard after generating a plan; replacing it
// with a no-op keeps the test output free of noise the app cannot fix.
// Unconditional, because the jsdom version exists and is the one that throws.
globalThis.scrollTo = () => {}

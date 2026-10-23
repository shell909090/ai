import { Plugin } from '@opencode/plugin'
import { createLogbook } from './core.mjs'

export default Plugin.define({
  id: 'session-logbook',
  setup: async (context) => createLogbook(context).start(),
})

// Compatibility export for the first web preview. Desktop owns the preset now.
import {embodiedPreset as preset} from './plugin/preset.mjs';
export function embodiedPreset(_here, mcpConfig) {return preset(mcpConfig);}

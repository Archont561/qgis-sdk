/**
 * Import for the side effect: every element of the catalogue registered.
 * `DEFINED` lists the tags this import registered (a tag another script
 * took first is not among them), and gives the entry a declaration file.
 */

import { defineElements } from "./index";

export const DEFINED: readonly string[] = defineElements();

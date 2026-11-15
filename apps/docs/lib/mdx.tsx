/**
 * The one component map every route renders MDX with.
 *
 * Fumadocs ships the components; nothing ships the registry. A page that names
 * `<Steps>` fails the build unless the component is passed to `<MDXContent>`
 * inside the `components` map, and a route with two maps (one for prose pages,
 * one for the landing page) is how the two drift apart: a guide renders its
 * callouts, the landing page throws on the same tag, or - worse - a page is
 * authored in `.md` and its JSX is dropped with the build still green.
 *
 * So the map lives here, `app/[...slug]/page.tsx` passes it and nothing else,
 * `app/page.tsx` composes its own markup from the same exports, and
 * `tests/mdx-registry.test.ts` asserts no route imports a Fumadocs component
 * from anywhere but this file.
 *
 * The named exports are the same objects the map carries: a page that needs a
 * card in its own JSX imports `Card` from here rather than from
 * `fumadocs-ui/components/card`, so an upgrade lands in one file.
 */

import { Accordion, Accordions } from "fumadocs-ui/components/accordion";
import { Banner } from "fumadocs-ui/components/banner";
import {
	Callout,
	CalloutDescription,
	CalloutTitle,
} from "fumadocs-ui/components/callout";
import { Card, Cards } from "fumadocs-ui/components/card";
import { File, Files, Folder } from "fumadocs-ui/components/files";
import { ImageZoom } from "fumadocs-ui/components/image-zoom";
import { InlineTOC } from "fumadocs-ui/components/inline-toc";
import { Step, Steps } from "fumadocs-ui/components/steps";
import { Tab, Tabs } from "fumadocs-ui/components/tabs";
import { TypeTable } from "fumadocs-ui/components/type-table";
import defaultMdxComponents from "fumadocs-ui/mdx";
import { CliWalkthrough } from "@/components/cli-walkthrough";
import { CompatNotice } from "@/components/compat-notice";
import { RegistryStats } from "@/components/registry-stats";
import { Versions } from "@/components/versions";

export {
	Accordion,
	Accordions,
	Banner,
	Callout,
	CalloutDescription,
	CalloutTitle,
	Card,
	Cards,
	CliWalkthrough,
	CompatNotice,
	File,
	Files,
	Folder,
	ImageZoom,
	InlineTOC,
	RegistryStats,
	Step,
	Steps,
	Tab,
	Tabs,
	TypeTable,
	Versions,
};

/** The names the registry must carry; the phases of TASK-170 name them. */
export const COMPONENT_NAMES = [
	"Callout",
	"Card",
	"Cards",
	"Steps",
	"Step",
	"Tabs",
	"Tab",
	"Files",
	"Folder",
	"File",
	"TypeTable",
	"Accordion",
	"Accordions",
	"Banner",
	"InlineTOC",
	"ImageZoom",
] as const;

/**
 * What `<MDXContent components={...}>` receives.
 *
 * `defaultMdxComponents` stays spread first: it carries the code block, the
 * heading and the link components the generated pages already rely on, and a
 * registry that replaced it would lose syntax highlighting while looking
 * complete.
 */
export const mdxComponents = {
	...defaultMdxComponents,
	Accordion,
	Accordions,
	Banner,
	Callout,
	CalloutDescription,
	CalloutTitle,
	Card,
	Cards,
	CliWalkthrough,
	CompatNotice,
	File,
	Files,
	Folder,
	ImageZoom,
	InlineTOC,
	RegistryStats,
	Step,
	Steps,
	Tab,
	Tabs,
	TypeTable,
	Versions,
};

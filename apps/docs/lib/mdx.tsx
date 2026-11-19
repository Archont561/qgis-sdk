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
 *
 * The `Pdx*` components render the Python reference fumero writes
 * (decision-86). They are registered here for the same reason as the rest:
 * `content/docs/reference/python/` is a build product, so nothing in this
 * repository authors those tags by hand, and the only place that can notice a
 * missing one is the map every route renders through.
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
import {
	PdxAttribute,
	PdxAttributes,
	PdxConstructor,
	PdxFunction,
	PdxParameter,
	PdxParameters,
	PdxRef,
	PdxReturns,
	PdxSource,
} from "@/components/mdx/pdx-components";
import { RegistryStats } from "@/components/registry-stats";
import { Versions } from "@/components/versions";

export { COMPONENT_NAMES } from "./mdx-names";
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
	PdxAttribute,
	PdxAttributes,
	PdxConstructor,
	PdxFunction,
	PdxParameter,
	PdxParameters,
	PdxRef,
	PdxReturns,
	PdxSource,
	RegistryStats,
	Step,
	Steps,
	Tab,
	Tabs,
	TypeTable,
	Versions,
};

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
	PdxAttribute,
	PdxAttributes,
	PdxConstructor,
	PdxFunction,
	PdxParameter,
	PdxParameters,
	PdxRef,
	PdxReturns,
	PdxSource,
	RegistryStats,
	Step,
	Steps,
	Tab,
	Tabs,
	TypeTable,
	Versions,
};

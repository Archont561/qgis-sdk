/**
 * The editorial half of the API index: one sentence per public module, and the
 * guide section that explains it.
 *
 * The names and their shapes are read from `api/python.json` and cannot drift;
 * this file answers the two questions the inventory cannot - what a module is
 * for, and where a reader should go next. A module that appears in the
 * inventory and not here fails the docs suite rather than rendering as a bare
 * table, and a `heading` that the guide no longer carries fails it too.
 */

import type { ModuleNotes } from "./lib/api-index";

export const API_MODULE_NOTES: ModuleNotes = {
	qgis_sdk: {
		description:
			"The declarations a plugin is written with: the class, the decorated actions, jobs, tools and toolbar entries, and the description they produce.",
		section: { guide: "doc-12", heading: "Declarations" },
	},
	"qgis_sdk.algorithms": {
		description:
			"The Processing authoring surface: an algorithm written as a declaration, the parameter kinds it takes, and the call that runs it.",
		section: {
			guide: "doc-12",
			heading: "Processing algorithms and safe outputs",
		},
	},
	"qgis_sdk.app": {
		description:
			"Running a plugin as a standalone application: the session, the backend it draws through, the shutdown report and the argv parser.",
		section: { guide: "doc-12", heading: "Running an app: `qgis-sdk run`" },
	},
	"qgis_sdk.batch": {
		description:
			"Several algorithm requests as one job: the request vocabulary, the items it carries and the body the job runs.",
		section: {
			guide: "doc-12",
			heading: "Processing algorithms and safe outputs",
		},
	},
	"qgis_sdk.bindings": {
		description:
			"The Desktop bindings behind `@toolbar`, `@menu` and `@shortcut`, and the description they add to an action.",
		section: {
			guide: "doc-12",
			heading: "Desktop bindings and native surfaces",
		},
	},
	"qgis_sdk.console": {
		description:
			"The Python console session a scaffolded plugin is bound into, and the handles that reload it.",
		section: { guide: "doc-12", heading: "From the QGIS Python console" },
	},
	"qgis_sdk.core": {
		description:
			"The contexts a handler receives and the runtime that builds them, one frozen record per set of capabilities.",
		section: { guide: "doc-12", heading: "Scoped plugin runtime" },
	},
	"qgis_sdk.declarations": {
		description:
			"The machinery behind the decorators: attribute keys, metadata, hint resolution, schema generation and the describe passes a host extends.",
		section: { guide: "doc-12", heading: "Declarations" },
	},
	"qgis_sdk.deprecation": {
		description:
			"The mark that gives a name a removal window, and the reader the inventory and `check` use to find it.",
		section: { guide: "doc-12", heading: "Stability" },
	},
	"qgis_sdk.environment": {
		description:
			"The variables the harnesses read - the test target, the dev server, the reload request - and the values they hold.",
		section: {
			guide: "doc-12",
			heading: "Developing against QGIS: `qgis-sdk dev`",
		},
	},
	"qgis_sdk.exports": {
		description:
			"Writing an algorithm's output to a file: the plan, the drivers a destination may name, and the run that produces it.",
	},
	"qgis_sdk.files": {
		description:
			"The `Files` service a context exposes as `ctx.files`: a `FileRef` in, a path under a grant out.",
		section: {
			guide: "doc-12",
			heading: "Desktop bindings and native surfaces",
		},
	},
	"qgis_sdk.http": {
		description:
			"The HTTP server a plugin can run inside the host, and the error one raises when it is refused.",
		section: {
			guide: "doc-12",
			heading: "Grants, the console and the HTTP allowlist",
		},
	},
	"qgis_sdk.jobs": {
		description:
			"Scoped jobs: the handle a caller holds, the events it observes, the faults it catches and the service behind `@job`.",
		section: { guide: "doc-12", heading: "Scoped jobs" },
	},
	"qgis_sdk.models": {
		description:
			"Every value that crosses a service boundary - layers, features, renderers, layouts, connections, network requests - and the errors the SDK raises.",
		section: { guide: "doc-12", heading: "Pure contract layer" },
	},
	"qgis_sdk.network": {
		description:
			"The network client and its defaults, the grant an outbound request needs, and the OGC API Features reader.",
		section: { guide: "doc-12", heading: "Networking" },
	},
	"qgis_sdk.processing": {
		description:
			"The parameter vocabulary a Processing algorithm is written in, and the catalogue of providers every host carries.",
		section: {
			guide: "doc-12",
			heading: "Providers: algorithms in the QGIS Processing toolbox",
		},
	},
	"qgis_sdk.providers": {
		description:
			"Declaring a provider of your own and the parameters its algorithms accept.",
		section: {
			guide: "doc-12",
			heading: "Providers: algorithms in the QGIS Processing toolbox",
		},
	},
	"qgis_sdk.server": {
		description:
			"Server hooks: the request, response and context a filter, a service or an access-control hook receives, and the decorators that declare them.",
		section: {
			guide: "doc-12",
			heading: "Desktop host: `host()` and the project manifest",
		},
	},
	"qgis_sdk.services": {
		description:
			"The Protocols a context carries - layers, features, canvas, layouts, styles, jobs - one per capability, each with a fake and a native adapter.",
		section: { guide: "doc-12", heading: "Pure contract layer" },
	},
	"qgis_sdk.testing": {
		description:
			"The fakes a pure test runs against, and the helpers a test uses to declare what a project needs.",
		section: { guide: "doc-12", heading: "Running tests: `qgis-sdk test`" },
	},
	"qgis_sdk.ui": {
		description:
			"The component catalogue an action's window is built from, and the description of the surface it renders into.",
		section: {
			guide: "doc-12",
			heading: "Forms: an action's inputs as a window",
		},
	},
};

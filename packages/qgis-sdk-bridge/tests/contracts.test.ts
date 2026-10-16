import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@archont561/bun-test-utils";
import Ajv2020 from "ajv/dist/2020.js";
import { compileFromFile } from "json-schema-to-typescript";

const contractNames = [
	"run-request",
	"run-result-reader",
	"run-result-writer",
] as const;
type ContractName = (typeof contractNames)[number];
type Case = {
	name: string;
	schema: ContractName;
	valid: boolean;
	value: unknown;
};

const contractsDir = new URL("./contracts/", import.meta.url);
const cases = JSON.parse(
	readFileSync(fileURLToPath(new URL("cases.json", contractsDir)), "utf8"),
) as Case[];
const ajv = new Ajv2020({
	allErrors: true,
	coerceTypes: false,
	useDefaults: false,
	removeAdditional: false,
});

function schemaPath(name: ContractName): string {
	return fileURLToPath(
		new URL(`generated/schemas/${name}.schema.json`, contractsDir),
	);
}

function declarationPath(name: ContractName): string {
	return fileURLToPath(
		new URL(`generated/types/${name}.schema.d.ts`, contractsDir),
	);
}

function pydanticSchemaPath(name: ContractName): string {
	return fileURLToPath(
		new URL(
			`pydantic/generated/schemas/pydantic-${name}.schema.json`,
			contractsDir,
		),
	);
}

function pydanticDeclarationPath(name: ContractName): string {
	return fileURLToPath(
		new URL(
			`pydantic/generated/types/pydantic-${name}.schema.d.ts`,
			contractsDir,
		),
	);
}

const validators = Object.fromEntries(
	contractNames.map((name) => [
		name,
		ajv.compile(JSON.parse(readFileSync(schemaPath(name), "utf8"))),
	]),
);
const pydanticValidators = Object.fromEntries(
	contractNames.map((name) => [
		name,
		ajv.compile(JSON.parse(readFileSync(pydanticSchemaPath(name), "utf8"))),
	]),
);

for (const sample of cases) {
	test(sample.name, () => {
		const validate = validators[sample.schema];
		expect(validate).toBeDefined();
		const value = structuredClone(sample.value);
		expect(validate(value)).toBe(sample.valid);
		expect(value).toEqual(sample.value);
	});

	test(`Pydantic schema: ${sample.name}`, () => {
		const validate = pydanticValidators[sample.schema];
		expect(validate).toBeDefined();
		const value = structuredClone(sample.value);
		expect(validate(value)).toBe(sample.valid);
		expect(value).toEqual(sample.value);
	});
}

test("only the declared TypeScript bindings are checked in", () => {
	const typesDir = fileURLToPath(new URL("generated/types/", contractsDir));
	expect(readdirSync(typesDir).sort()).toEqual(
		contractNames.map((name) => `${name}.schema.d.ts`).sort(),
	);
});

test("only the declared Pydantic schemas and bindings are checked in", () => {
	const schemasDir = fileURLToPath(
		new URL("pydantic/generated/schemas/", contractsDir),
	);
	const typesDir = fileURLToPath(
		new URL("pydantic/generated/types/", contractsDir),
	);
	expect(readdirSync(schemasDir).sort()).toEqual(
		contractNames.map((name) => `pydantic-${name}.schema.json`).sort(),
	);
	expect(readdirSync(typesDir).sort()).toEqual(
		contractNames.map((name) => `pydantic-${name}.schema.d.ts`).sort(),
	);
});

for (const name of contractNames) {
	test(`${name} TypeScript declaration matches its JSON Schema`, async () => {
		const generated = await compileFromFile(schemaPath(name));
		const checkedIn = readFileSync(declarationPath(name), "utf8");
		expect(checkedIn).toBe(generated);
	});

	test(`Pydantic ${name} TypeScript declaration matches its JSON Schema`, async () => {
		const generated = await compileFromFile(pydanticSchemaPath(name));
		const checkedIn = readFileSync(pydanticDeclarationPath(name), "utf8");
		expect(checkedIn).toBe(generated);
	});
}

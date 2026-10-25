import type { RunRequest } from "./contracts/generated/types/run-request.schema";
import type { RunResultReader } from "./contracts/generated/types/run-result-reader.schema";
import type { RunResultWriter } from "./contracts/generated/types/run-result-writer.schema";
import type { RunRequest as PydanticRunRequest } from "./contracts/pydantic/generated/types/pydantic-run-request.schema";
import type { RunResultReader as PydanticRunResultReader } from "./contracts/pydantic/generated/types/pydantic-run-result-reader.schema";
import type { RunResult as PydanticRunResultWriter } from "./contracts/pydantic/generated/types/pydantic-run-result-writer.schema";

const request: RunRequest = { kind: "run", count: 2 };
const reader: RunResultReader = { processed: 2, revision: "v2" };
const writer: RunResultWriter = { processed: 2, note: null };
const pydanticRequest: PydanticRunRequest = { kind: "run", count: 2 };
const pydanticReader: PydanticRunResultReader = {
	processed: 2,
	revision: "v2",
};
const pydanticWriter: PydanticRunResultWriter = { processed: 2, note: null };
void [request, reader, writer, pydanticRequest, pydanticReader, pydanticWriter];

// @ts-expect-error Writer serialization includes the defaulted note.
const missingSerializedDefault: RunResultWriter = { processed: 2 };
// @ts-expect-error A defaulted string mode is not nullable.
const nullableMode: RunRequest = { kind: "run", count: 2, mode: null };
// @ts-expect-error A reader recognizes only the declared compatible field.
const unexpectedResult: RunResultReader = { processed: 2, surprise: "v2" };
// @ts-expect-error The Pydantic writer serializes its defaulted nullable field.
const missingPydanticDefault: PydanticRunResultWriter = { processed: 2 };
const unexpectedPydanticResult: PydanticRunResultReader = {
	processed: 2,
	// @ts-expect-error The Pydantic reader recognizes only its named extension.
	surprise: "v2",
};
void [
	missingSerializedDefault,
	nullableMode,
	unexpectedResult,
	missingPydanticDefault,
	unexpectedPydanticResult,
];

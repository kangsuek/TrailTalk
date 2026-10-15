// 자동 생성 파일(npm run gen:api). 직접 고치지 않는다.

export interface paths {
    "/api/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_api_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Session */
        post: operations["create_session_api_sessions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/sessions/prepare": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Prepare Session
         * @description 대화 화면이 열리면 부른다. 다음 대화의 CLI를 미리 띄워 인사말 대기를 줄인다(사용량 없음).
         */
        post: operations["prepare_session_api_sessions_prepare_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/sessions/{session_id}/turns": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Turn */
        post: operations["create_turn_api_sessions__session_id__turns_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/sessions/{session_id}/end": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * End Session
         * @description 세션을 끝내고 일지 정리를 띄운 뒤, 정리가 끝나길 잠깐 기다려 마무리 멘트를 준다(멱등).
         */
        post: operations["end_session_api_sessions__session_id__end_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/profile": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Profile */
        get: operations["get_profile_api_profile_get"];
        /** Put Profile */
        put: operations["put_profile_api_profile_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/journal": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Journal
         * @description 현지 날짜 범위(from~to, 둘 다 포함)의 일지. 기본은 최근 30일. 최신순.
         *
         *     사용자가 한마디도 하지 않은 대화(인사말만 있는 것)는 빼고 준다.
         */
        get: operations["list_journal_api_journal_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/journal/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Journal */
        get: operations["get_journal_api_journal__session_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/notes/{note_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Note */
        patch: operations["update_note_api_notes__note_id__patch"];
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** GreetingOut */
        GreetingOut: {
            /** Turn Id */
            turn_id: string;
            /** Text */
            text: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** JournalDetail */
        JournalDetail: {
            session: components["schemas"]["JournalItem"];
            /** Notes */
            notes: components["schemas"]["NoteOut"][];
            /** Turns */
            turns: components["schemas"]["TurnOut"][];
        };
        /** JournalItem */
        JournalItem: {
            /** Id */
            id: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /** Ended At */
            ended_at: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "active" | "paused" | "ended";
            /** Title */
            title: string | null;
            /** Summary */
            summary: string[];
            /** Tags */
            tags: string[];
            /** Journal Status */
            journal_status: ("pending" | "done" | "failed") | null;
            counts: components["schemas"]["NoteCounts"];
        };
        /** NoteCounts */
        NoteCounts: {
            /** Idea */
            idea: number;
            /** Todo */
            todo: number;
            /** Memo */
            memo: number;
        };
        /** NoteOut */
        NoteOut: {
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "idea" | "todo" | "memo";
            /** Content */
            content: string;
            /** Starred */
            starred: boolean;
            /** Done */
            done: boolean;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /**
         * NotePatch
         * @description 보낸 필드만 바꾼다.
         */
        NotePatch: {
            /** Starred */
            starred?: boolean | null;
            /** Done */
            done?: boolean | null;
            /** Content */
            content?: string | null;
        };
        /**
         * PersonaOut
         * @description 화면에 보일 캐릭터 정보. 클라이언트는 캐릭터 이름을 코드에 두지 않고 이 값을 쓴다(NFR-08).
         */
        PersonaOut: {
            /** Id */
            id: string;
            /** Name */
            name: string;
        };
        /** ProfileOut */
        ProfileOut: {
            /** Nickname */
            nickname: string | null;
            /** Interests */
            interests: string[];
            /** Persona Id */
            persona_id: string;
            /** Voice */
            voice: string | null;
            /** Keep Audio */
            keep_audio: boolean;
        };
        /**
         * ProfileUpdate
         * @description 보낸 필드만 바꾼다. nickname을 null로 보내면 기본 호칭으로 돌아간다.
         */
        ProfileUpdate: {
            /** Nickname */
            nickname?: string | null;
            /**
             * Interests
             * @default []
             */
            interests: string[];
            /** Persona Id */
            persona_id?: string | null;
            /** Voice */
            voice?: string | null;
            /**
             * Keep Audio
             * @default false
             */
            keep_audio: boolean;
        };
        /** SavedCounts */
        SavedCounts: {
            /** Idea */
            idea: number;
            /** Todo */
            todo: number;
            /** Memo */
            memo: number;
        };
        /**
         * SessionClosed
         * @description 끝내기 응답. closing은 캐릭터가 하는 마무리 멘트, saved는 이 대화에서 저장한 노트 개수다.
         *
         *     journal_status가 pending이면 일지 정리가 아직 끝나지 않은 것이다(개수가 나중에 늘 수 있다).
         */
        SessionClosed: {
            session: components["schemas"]["SessionOut"];
            /** Closing */
            closing: string;
            saved: components["schemas"]["SavedCounts"];
            /** Journal Status */
            journal_status: ("pending" | "done" | "failed") | null;
        };
        /** SessionCreate */
        SessionCreate: {
            /**
             * Mode
             * @default text
             * @enum {string}
             */
            mode: "text" | "voice";
        };
        /** SessionOut */
        SessionOut: {
            /** Id */
            id: string;
            /**
             * Mode
             * @enum {string}
             */
            mode: "text" | "voice";
            /**
             * Status
             * @enum {string}
             */
            status: "active" | "paused" | "ended";
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /** Ended At */
            ended_at: string | null;
        };
        /** SessionStarted */
        SessionStarted: {
            session: components["schemas"]["SessionOut"];
            greeting: components["schemas"]["GreetingOut"];
            persona: components["schemas"]["PersonaOut"];
        };
        /** TurnCreate */
        TurnCreate: {
            /** Text */
            text: string;
        };
        /** TurnOut */
        TurnOut: {
            /** Id */
            id: string;
            /** Seq */
            seq: number;
            /**
             * Role
             * @enum {string}
             */
            role: "user" | "assistant";
            /** Text */
            text: string;
            /** Interrupted */
            interrupted: boolean;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
        /**
         * DoneEvent
         * @description 턴 끝. session_status가 paused/ended면 도구(pause_session/end_session)가 바꾼 것이다.
         */
        DoneEvent: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "done";
            /** Turn Id */
            turn_id: string;
            /** Text */
            text: string;
            /**
             * Interrupted
             * @default false
             */
            interrupted: boolean;
            /**
             * Session Status
             * @default active
             * @enum {string}
             */
            session_status: "active" | "paused" | "ended";
        };
        /**
         * ErrorEvent
         * @description 스트림 도중 오류. code는 공통 오류 형식(클라이언트 규약 7절)과 같은 값이다.
         */
        ErrorEvent: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "error";
            /** Code */
            code: string;
            /** Message */
            message: string;
        };
        /**
         * SentenceEvent
         * @description 캐릭터 답변의 한 문장. index는 턴 안에서 0부터 증가한다(3단계에서 audio 추가).
         */
        SentenceEvent: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "sentence";
            /** Index */
            index: number;
            /** Text */
            text: string;
        };
        /**
         * ToolEvent
         * @description 도구 사용. start(이름만, 검색 중 표시) → call(입력 완성) → end(결과 요약) 순서로 온다.
         */
        ToolEvent: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "tool";
            /**
             * Phase
             * @enum {string}
             */
            phase: "start" | "call" | "end";
            /** Tool Use Id */
            tool_use_id: string;
            /** Name */
            name: string;
            /**
             * Input
             * @default null
             */
            input: {
                [key: string]: unknown;
            } | null;
            /**
             * Summary
             * @default null
             */
            summary: {
                [key: string]: unknown;
            } | null;
            /**
             * Is Error
             * @default false
             */
            is_error: boolean;
        };
        /**
         * TurnEvent
         * @description 스트림의 첫 이벤트. turn_id는 이번 답변(assistant 턴)의 ID로 끼어들기(S3-04)에 쓴다.
         */
        TurnEvent: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "turn";
            /** Turn Id */
            turn_id: string;
        };
        StreamEvent: components["schemas"]["TurnEvent"] | components["schemas"]["SentenceEvent"] | components["schemas"]["ToolEvent"] | components["schemas"]["DoneEvent"] | components["schemas"]["ErrorEvent"];
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    health_api_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
    create_session_api_sessions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SessionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionStarted"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    prepare_session_api_sessions_prepare_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SessionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_turn_api_sessions__session_id__turns_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TurnCreate"];
            };
        };
        responses: {
            /** @description 턴 이벤트 스트림(turn → sentence·tool → done 또는 error) */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": components["schemas"]["StreamEvent"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    end_session_api_sessions__session_id__end_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionClosed"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_profile_api_profile_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProfileOut"];
                };
            };
        };
    };
    put_profile_api_profile_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProfileUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProfileOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_journal_api_journal_get: {
        parameters: {
            query?: {
                from?: string | null;
                to?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JournalItem"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_journal_api_journal__session_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JournalDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_note_api_notes__note_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                note_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NotePatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NoteOut"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}

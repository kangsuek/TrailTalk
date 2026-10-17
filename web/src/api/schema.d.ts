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
    "/api/sessions/{session_id}/turns/{turn_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Cancel Turn
         * @description 끼어들기(계획서 S3-04): 답변을 멈추고 들려준 문장까지만 기록한다. 끝난 턴도 받는다(멱등).
         */
        post: operations["cancel_turn_api_sessions__session_id__turns__turn_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/sessions/{session_id}/turns/audio": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Audio Turn
         * @description 말 한 번(오디오)을 받아 인식한 뒤 텍스트 턴과 같은 SSE로 답한다(계획서 S3-03).
         *
         *     인식은 SSE를 열기 전에 하므로 오디오·인식 오류와 말 없음(no_speech)은 JSON 오류로 간다.
         */
        post: operations["create_audio_turn_api_sessions__session_id__turns_audio_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/sessions/{session_id}/turns/audio/record": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Record Audio Turn
         * @description 오프라인 큐의 말을 대답 없이 기록만 남긴다(계획서 S3-12). 끝난 대화도 받는다.
         *
         *     서버가 이미 대화를 끝냈거나(30분 넘게 끊김) 페이지를 새로 열어 대답할 수 없는 말의
         *     유실을 막는다.
         */
        post: operations["record_audio_turn_api_sessions__session_id__turns_audio_record_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/sessions/{session_id}/turns/{turn_id}/latency": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Report Latency
         * @description 음성 턴의 지연을 보고한다(계획서 S3-07). 측정 행이 없으면 404 turn_not_found.
         */
        post: operations["report_latency_api_sessions__session_id__turns__turn_id__latency_post"];
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
    "/api/voices": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Voices */
        get: operations["list_voices_api_voices_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/voices/{voice}/sample": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Voice Sample
         * @description 보이스를 고정 문장으로 미리 들려준다(보이스·속도별로 한 번만 합성해 둔다).
         */
        get: operations["voice_sample_api_voices__voice__sample_get"];
        put?: never;
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
        /**
         * Get Journal
         * @description 일지 상세. 목록에서 빠지는 대화(사용자 발화 없음)도 ID로는 조회된다.
         */
        get: operations["get_journal_api_journal__session_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Journal
         * @description 대화를 지운다(전문·노트·지연 기록·보관한 녹음까지). 진행 중인 대화는 409 session_active,
         *     답변을 만드는 중이면 409 turn_in_progress. 쉬는 중이면 CLI를 정리하고, 돌던 일지 정리는 멈춘다.
         */
        delete: operations["delete_journal_api_journal__session_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Journal
         * @description 대화 제목을 고친다. 고친 제목은 일지를 다시 정리해도 바뀌지 않는다.
         */
        patch: operations["update_journal_api_journal__session_id__patch"];
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
    "/api/journal/{session_id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Retry Journal
         * @description 정리에 실패한(또는 정리 기록이 없는) 끝난 대화, 예전 형식으로 정리된 대화를 다시 정리한다.
         *     정리 중이거나 새 형식으로 정리를 마쳤으면 그대로 둔다.
         *
         *     정리는 백그라운드로 돈다. 응답의 journal_status가 pending이면 상세를 다시 불러와 끝을 본다.
         */
        post: operations["retry_journal_api_journal__session_id__retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/latency": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Latency
         * @description 최근 음성 턴부터 limit개의 지연과 요약(중앙값·90% 값).
         */
        get: operations["latency_api_latency_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AudioConfig */
        AudioConfig: {
            upload: components["schemas"]["UploadAudioConfig"];
            response: components["schemas"]["ResponseAudioConfig"];
        };
        /** CitationOut */
        CitationOut: {
            /** N */
            n: number;
            /** Title */
            title: string;
            /** Url */
            url: string;
        };
        /** ClientConfig */
        ClientConfig: {
            vad: components["schemas"]["VadConfig"];
            session: components["schemas"]["ClientSessionConfig"];
            audio: components["schemas"]["AudioConfig"];
            /** Offline Notice */
            offline_notice: string;
        };
        /** ClientSessionConfig */
        ClientSessionConfig: {
            /** Idle Timeout Minutes */
            idle_timeout_minutes: number;
        };
        /** GreetingOut */
        GreetingOut: {
            /** Turn Id */
            turn_id: string;
            /** Text */
            text: string;
            /** Audio */
            audio: string | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** JournalDetail */
        JournalDetail: {
            session: components["schemas"]["JournalItem"];
            /** Summary Cites */
            summary_cites: number[][];
            /** Citations */
            citations: components["schemas"]["CitationOut"][];
            /** Checks */
            checks: string[] | null;
            /** Persona Name */
            persona_name: string;
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
            /** Topics */
            topics: string[];
            /** Journal Status */
            journal_status: ("pending" | "done" | "failed") | null;
            counts: components["schemas"]["NoteCounts"];
        };
        /** JournalPatch */
        JournalPatch: {
            /** Title */
            title: string;
        };
        /** LatencyOut */
        LatencyOut: {
            /** Turns */
            turns: components["schemas"]["LatencyTurn"][];
            summary: components["schemas"]["LatencySummary"];
        };
        /**
         * LatencyReport
         * @description 웹이 잰 지연(ms, S3-07): 말 끝 → 요청 시작, 요청 시작 → 첫 소리.
         *     first_sound_notice: 첫 소리가 검색 안내 음성이었다.
         */
        LatencyReport: {
            /** Speech To Request Ms */
            speech_to_request_ms: number;
            /** Request To Playback Ms */
            request_to_playback_ms: number;
            /**
             * First Sound Notice
             * @default false
             */
            first_sound_notice: boolean;
        };
        /** LatencySummary */
        LatencySummary: {
            /** Count */
            count: number;
            total_ms: components["schemas"]["Spread"];
            total_ms_reply: components["schemas"]["Spread"];
            /** Stages */
            stages: {
                [key: string]: number | null;
            };
        };
        /** LatencyTurn */
        LatencyTurn: {
            /** Turn Id */
            turn_id: string;
            /** Session Id */
            session_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Audio Bytes */
            audio_bytes: number | null;
            /** Upload Ms */
            upload_ms: number | null;
            /** Stt Ms */
            stt_ms: number | null;
            /** First Token Ms */
            first_token_ms: number | null;
            /** First Sentence Ms */
            first_sentence_ms: number | null;
            /** Done Ms */
            done_ms: number | null;
            /** Speech To Request Ms */
            speech_to_request_ms: number | null;
            /** Request To Playback Ms */
            request_to_playback_ms: number | null;
            /** First Sound Notice */
            first_sound_notice: boolean | null;
            /** Total Ms */
            total_ms: number | null;
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
            /** Cites */
            cites: number[];
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
            /** Speaking Rate */
            speaking_rate: number | null;
            /** Keep Audio */
            keep_audio: boolean;
            client: components["schemas"]["ClientConfig"];
        };
        /**
         * ProfileUpdate
         * @description 보낸 필드만 바꾼다. nickname·voice·speaking_rate를 null로 보내면 기본값으로 돌아간다.
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
            voice?: ("alloy" | "ash" | "ballad" | "cedar" | "coral" | "echo" | "fable" | "marin" | "nova" | "onyx" | "sage" | "shimmer" | "verse") | null;
            /** Speaking Rate */
            speaking_rate?: number | null;
            /**
             * Keep Audio
             * @default false
             */
            keep_audio: boolean;
        };
        /** RecordedTurn */
        RecordedTurn: {
            /** Text */
            text: string;
        };
        /** ResponseAudioConfig */
        ResponseAudioConfig: {
            /**
             * Codec
             * @constant
             */
            codec: "mp3";
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
            /** Closing Audio */
            closing_audio: string | null;
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
        /** Spread */
        Spread: {
            /** Median */
            median: number | null;
            /** P90 */
            p90: number | null;
        };
        /**
         * TurnCancel
         * @description 끼어들기: 다 들려준 마지막 문장 번호(sentence.index). 하나도 못 들려줬으면 -1.
         */
        TurnCancel: {
            /** Last Played */
            last_played: number;
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
        /** UploadAudioConfig */
        UploadAudioConfig: {
            /**
             * Codec
             * @constant
             */
            codec: "opus";
            /**
             * Sample Rate Hz
             * @constant
             */
            sample_rate_hz: 16000;
            /**
             * Channels
             * @constant
             */
            channels: 1;
        };
        /**
         * VadConfig
         * @description Silero VAD 확률 임계값과 발화 길이. 재생 중(setVadMode playback)에는 playback_* 값을 쓴다.
         */
        VadConfig: {
            /** Speech Threshold */
            speech_threshold: number;
            /** Silence Threshold */
            silence_threshold: number;
            /** Playback Speech Threshold */
            playback_speech_threshold: number;
            /** Playback Silence Threshold */
            playback_silence_threshold: number;
            /** End Of Speech Silence Ms */
            end_of_speech_silence_ms: number;
            /** Min Speech Ms */
            min_speech_ms: number;
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
         * VoicesOut
         * @description 설정 화면에서 고를 수 있는 보이스와 캐릭터 기본값(페르소나 YAML).
         */
        VoicesOut: {
            /** Voices */
            voices: string[];
            /** Default Voice */
            default_voice: string;
            /** Default Rate */
            default_rate: number;
            /** Min Rate */
            min_rate: number;
            /** Max Rate */
            max_rate: number;
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
         * @description 캐릭터 답변의 한 문장. index는 턴 안에서 0부터 증가한다.
         *
         *     audio는 그 문장의 MP3(base64)다. 음성 세션에서만 있고, 합성에 실패하면 null이다.
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
            /**
             * Audio
             * @default null
             */
            audio: string | null;
        };
        /** SummaryLink */
        SummaryLink: {
            /** Title */
            title: string | null;
            /** Url */
            url: string;
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
            summary: (components["schemas"]["WebSearchSummary"] | components["schemas"]["WebFetchSummary"] | components["schemas"]["ToolResultSummary"]) | null;
            /**
             * Is Error
             * @default false
             */
            is_error: boolean;
            /** @default null */
            notice: components["schemas"]["VoiceNotice"] | null;
        };
        /**
         * ToolResultSummary
         * @description 앱 도구(save_note 등) 결과. result는 도구가 돌려준 값(보통 문자열).
         */
        ToolResultSummary: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "result";
            /** Result */
            result: unknown;
        };
        /**
         * TranscriptEvent
         * @description 음성 업로드의 인식 결과(사용자 메시지로 저장된 글). 음성 턴 스트림의 첫 이벤트다.
         */
        TranscriptEvent: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "transcript";
            /** Text */
            text: string;
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
        /**
         * VoiceNotice
         * @description 답변이 아닌 안내 음성(예: 검색 전 "잠깐 찾아볼게요"). audio는 MP3(base64) 또는 null.
         */
        VoiceNotice: {
            /** Text */
            text: string;
            /** Audio */
            audio: string | null;
        };
        /**
         * WebFetchSummary
         * @description 페이지 읽기 결과 요약. code는 HTTP 상태, host는 출처 표시용 호스트 이름.
         */
        WebFetchSummary: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "web_fetch";
            /** Code */
            code: number | null;
            /** Bytes */
            bytes: number | null;
            /** Url */
            url: string | null;
            /** Host */
            host: string | null;
        };
        /**
         * WebSearchSummary
         * @description 웹 검색 결과 요약. sources는 링크의 호스트 이름(www. 뗌, 중복 없이 최대 3개)으로
         *     화면의 출처 표시에 쓴다.
         */
        WebSearchSummary: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "web_search";
            /** Query */
            query: string | null;
            /** Links */
            links: components["schemas"]["SummaryLink"][];
            /** Sources */
            sources: string[];
        };
        StreamEvent: components["schemas"]["TranscriptEvent"] | components["schemas"]["TurnEvent"] | components["schemas"]["SentenceEvent"] | components["schemas"]["ToolEvent"] | components["schemas"]["DoneEvent"] | components["schemas"]["ErrorEvent"];
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
    cancel_turn_api_sessions__session_id__turns__turn_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
                turn_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TurnCancel"];
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
    create_audio_turn_api_sessions__session_id__turns_audio_post: {
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
                "audio/webm": string;
                "audio/ogg": string;
                "audio/mp4": string;
                "audio/wav": string;
                "audio/mpeg": string;
            };
        };
        responses: {
            /** @description 음성 턴 이벤트 스트림(transcript → turn → sentence·tool → done 또는 error) */
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
    record_audio_turn_api_sessions__session_id__turns_audio_record_post: {
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
                "audio/webm": string;
                "audio/ogg": string;
                "audio/mp4": string;
                "audio/wav": string;
                "audio/mpeg": string;
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecordedTurn"];
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
    report_latency_api_sessions__session_id__turns__turn_id__latency_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
                turn_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LatencyReport"];
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
    list_voices_api_voices_get: {
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
                    "application/json": components["schemas"]["VoicesOut"];
                };
            };
        };
    };
    voice_sample_api_voices__voice__sample_get: {
        parameters: {
            query?: {
                rate?: number | null;
            };
            header?: never;
            path: {
                voice: "alloy" | "ash" | "ballad" | "cedar" | "coral" | "echo" | "fable" | "marin" | "nova" | "onyx" | "sage" | "shimmer" | "verse";
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 미리 듣기 MP3 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "audio/mpeg": unknown;
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
    delete_journal_api_journal__session_id__delete: {
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
    update_journal_api_journal__session_id__patch: {
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
                "application/json": components["schemas"]["JournalPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JournalItem"];
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
    retry_journal_api_journal__session_id__retry_post: {
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
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JournalItem"];
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
    latency_api_latency_get: {
        parameters: {
            query?: {
                limit?: number;
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
                    "application/json": components["schemas"]["LatencyOut"];
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

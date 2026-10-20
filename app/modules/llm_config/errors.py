from app.shared.errors import Conflict, Invalid, NotFound


class PresetNotFound(NotFound):
    code, error_code = "preset_not_found", "LLM_001"


class PresetInvalid(Invalid):
    code, error_code = "preset_invalid", "LLM_002"


class PresetNameTaken(Conflict):
    code, error_code = "preset_name_taken", "LLM_003"

    def __init__(self):
        super().__init__(field="name")


class DefaultPresetConflict(Conflict):
    code, error_code = "default_preset_conflict", "LLM_004"

from app.shared.errors import Invalid


class ThresholdOutOfRange(Invalid):
    code, error_code = "threshold_out_of_range", "TQ_001"

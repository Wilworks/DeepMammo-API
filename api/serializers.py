from rest_framework import serializers


class PredictRequestSerializer(serializers.Serializer):
    image = serializers.ImageField(
        help_text="Mammogram image — PNG or JPG, max 20MB"
    )


class ConfidenceSerializer(serializers.Serializer):
    label         = serializers.CharField()
    confidence    = serializers.FloatField()
    probabilities = serializers.DictField(child=serializers.FloatField())


class SegmentationSerializer(serializers.Serializer):
    mask_b64     = serializers.CharField()
    overlay_b64  = serializers.CharField()
    coverage_pct = serializers.FloatField()


class ClinicalReportSerializer(serializers.Serializer):
    full_text  = serializers.CharField()
    sections   = serializers.DictField(child=serializers.CharField())
    model_used = serializers.CharField()


class PredictResponseSerializer(serializers.Serializer):
    abnormality     = ConfidenceSerializer()
    pathology       = ConfidenceSerializer()
    segmentation    = SegmentationSerializer()
    gradcam_b64     = serializers.CharField()
    clinical_report = ClinicalReportSerializer()
    pdf_b64         = serializers.CharField()

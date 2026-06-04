from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from django.shortcuts import render
import json

from .serializers import PredictRequestSerializer
from inference.session import run_inference
from inference.preprocessor import MammographyPreprocessor
from inference.postprocess import postprocess
from inference.gradcam import generate_gradcam
from report.groq_client import generate_clinical_report
from report.pdf_builder import build_pdf


preprocessor = MammographyPreprocessor()


# ── Template views ─────────────────────────────────────────────────
def home(request):      return render(request, 'home.html')
def dashboard(request): return render(request, 'dashboard.html')
def tutorial(request):  return render(request, 'tutorial.html')
def faq(request):       return render(request, 'faq.html')


# ── API views ──────────────────────────────────────────────────────
class PredictView(APIView):
    parser_classes = [MultiPartParser]

    def post(self, request):
        # Pre-flight content length guard
        content_length = request.META.get('CONTENT_LENGTH')
        if content_length:
            try:
                if int(content_length) > 20 * 1024 * 1024:
                    return Response(
                        {'error': 'Upload size exceeds the 20MB limit. Please upload a smaller mammography specimen scan.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except (ValueError, TypeError):
                pass

        serializer = PredictRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        image_file  = serializer.validated_data['image']
        
        # File property guard
        if image_file.size > 20 * 1024 * 1024:
            return Response(
                {'error': 'File size exceeds the 20MB limit. Please upload a smaller mammography specimen scan.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        image_bytes = image_file.read()

        # Optional patient info passed as JSON string in form field
        patient_info = None
        raw_patient  = request.data.get('patient_info')
        if raw_patient:
            try:
                patient_info = json.loads(raw_patient)
            except (json.JSONDecodeError, TypeError):
                patient_info = None

        try:
            tensor, original_image  = preprocessor(image_bytes)
            raw_outputs             = run_inference(tensor)
            predictions             = postprocess(raw_outputs, original_image)
            gradcam_b64             = generate_gradcam(raw_outputs['seg_logits'], original_image)
            clinical_report         = generate_clinical_report(predictions, patient_info)

            images = {
                'original_b64': predictions['segmentation'].get('overlay_b64') or predictions['segmentation'].get('mask_b64'),
                'mask_b64':    predictions['segmentation']['mask_b64'],
                'overlay_b64': predictions['segmentation']['overlay_b64'],
                'gradcam_b64': gradcam_b64,
            }
            pdf_b64 = build_pdf(predictions, clinical_report, images)

            return Response({
                **predictions,
                'gradcam_b64':     gradcam_b64,
                'clinical_report': clinical_report,
                'pdf_b64':         pdf_b64,
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response(
                {'error': f'Invalid input data: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': 'An unexpected error occurred during diagnostic pipeline execution. Please verify the uploaded image format and try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class HealthView(APIView):
    def get(self, request):
        from inference.session import get_session
        try:
            session = get_session()
            return Response({
                'status':  'ok',
                'inputs':  [i.name for i in session.get_inputs()],
                'outputs': [o.name for o in session.get_outputs()],
            })
        except Exception as e:
            return Response({'status': 'error', 'detail': str(e)}, status=500)

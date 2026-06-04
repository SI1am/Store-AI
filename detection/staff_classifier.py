import logging
import numpy as np
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class StaffClassifier:
    def __init__(self, model_name: str = "efficientnet_b0", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None
        self._transform = None
        self.tried_loading = False

    def _lazy_load_model(self) -> None:
        """Lazy-loads torchvision's EfficientNet-B0 with fallback mechanisms."""
        if self.tried_loading:
            return
            
        self.tried_loading = True
        logger.info("Attempting to load torchvision EfficientNet-B0 model...")
        try:
            import torch
            import torchvision.models as models
            import torchvision.transforms as transforms
            
            # Load pre-trained EfficientNet-B0 model
            weights = models.EfficientNet_B0_Weights.DEFAULT
            model = models.efficientnet_b0(weights=weights)
            
            # Freeze weights
            for param in model.parameters():
                param.requires_grad = False
                
            # Replace classifier head with a custom linear layer (Binary: Staff vs Customer)
            # EfficientNet-B0 has 1280 out features in classifier[1]
            in_features = model.classifier[1].in_features
            model.classifier[1] = torch.nn.Linear(in_features, 2)
            
            # Load model to device
            model.to(self.device)
            model.eval()
            
            self._model = model
            # Setup image standard ImageNet transformations
            self._transform = transforms.Compose([
                transforms.ToPILImage(),
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])
            logger.info("torchvision EfficientNet-B0 successfully loaded.")
        except Exception as e:
            logger.warning(f"Could not load torchvision model (using heuristics fallback instead): {e}")

    def classify(self, cropped_patch: np.ndarray, y_center_pct: Optional[float] = None, frame_count: int = 0) -> Dict[str, Any]:
        """
        Classifies an image patch of a shopper as staff or customer.
        Utilizes both DL classification and spatial heuristics:
        - If shopper center is in top 20% of frame (y_center_pct < 0.2) AND seen >10 frames, mark as staff.
        """
        # Heuristic checks (Always prioritized for safety and speed)
        if y_center_pct is not None and y_center_pct < 0.2 and frame_count > 10:
            return {
                'is_staff': True,
                'confidence': 0.90,
                'reasoning': 'spatial_heuristic_top_frame_desk'
            }

        # Check patch size
        if cropped_patch is None or cropped_patch.size == 0 or cropped_patch.shape[0] < 40 or cropped_patch.shape[1] < 40:
            return {
                'is_staff': False,
                'confidence': 0.20,
                'reasoning': 'patch_too_small_fallback'
            }

        self._lazy_load_model()
        
        # If deep learning model loaded successfully, use it
        if self._model is not None and self._transform is not None:
            try:
                import torch
                # Transform image patch
                tensor = self._transform(cropped_patch).unsqueeze(0).to(self.device)
                with torch.no_grad():
                    outputs = self._model(tensor)
                    probabilities = torch.softmax(outputs, dim=1)
                    conf, preds = torch.max(probabilities, dim=1)
                    
                    is_staff_pred = bool(preds.item() == 1)
                    confidence_pred = float(conf.item())
                    
                    return {
                        'is_staff': is_staff_pred,
                        'confidence': confidence_pred,
                        'reasoning': 'efficientnet_b0_classifier'
                    }
            except Exception as e:
                logger.warning(f"DL inference failed, using fallback: {e}")
                
        # Default fallback (Customers are majority class)
        return {
            'is_staff': False,
            'confidence': 0.0,
            'reasoning': 'default_shoppers_majority_class'
        }

    def batch_classify(self, patches: List[np.ndarray]) -> List[Dict[str, Any]]:
        """Performs batch classification for performance optimization."""
        if not patches:
            return []

        self._lazy_load_model()
        
        if self._model is not None and self._transform is not None:
            try:
                import torch
                tensors = []
                for patch in patches:
                    if patch is not None and patch.size > 0:
                        tensors.append(self._transform(patch))
                    else:
                        # Dummy tensor for empty patches
                        tensors.append(torch.zeros((3, 224, 224)))
                        
                batch_tensor = torch.stack(tensors).to(self.device)
                with torch.no_grad():
                    outputs = self._model(batch_tensor)
                    probabilities = torch.softmax(outputs, dim=1)
                    confs, preds = torch.max(probabilities, dim=1)
                    
                    results = []
                    for idx, (conf, pred) in enumerate(zip(confs, preds)):
                        results.append({
                            'is_staff': bool(pred.item() == 1),
                            'confidence': float(conf.item()),
                            'reasoning': 'efficientnet_b0_batch_classifier'
                        })
                    return results
            except Exception as e:
                logger.warning(f"DL batch inference failed, falling back to sequential heuristic: {e}")
                
        # Fallback to sequential
        return [self.classify(p) for p in patches]

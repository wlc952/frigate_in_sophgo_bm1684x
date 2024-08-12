import sophon.sail as sail
import logging
import numpy as np
import os
import sys
import argparse

from pydantic import Field
from typing_extensions import Literal

from frigate.detectors.detection_api import DetectionApi
from frigate.detectors.detector_config import BaseDetectorConfig

logger = logging.getLogger(__name__)

DETECTOR_KEY = "sophgo"

class EngineOV:

    def __init__(self, model_path="", output_names="", device_id=0):
        if "DEVICE_ID" in os.environ:
            device_id = int(os.environ["DEVICE_ID"])
            # print(">>>> device_id is in os.environ. and device_id = ", device_id)
        self.model_path = model_path
        self.device_id = device_id
        try:
            self.model = sail.Engine(model_path, device_id, sail.IOMode.SYSIO)
        except Exception as e:
            print("load model error; please check model path and device status;")
            print(">>>> model_path: ", model_path)
            print(">>>> device_id: ", device_id)
            print(">>>> sail.Engine error: ", e)
            raise e
        self.graph_name = self.model.get_graph_names()[0]
        self.input_name = self.model.get_input_names(self.graph_name)
        self.output_name = self.model.get_output_names(self.graph_name)

    def __str__(self):
        return "EngineOV: model_path={}, device_id={}".format(self.model_path, self.device_id)

    def __call__(self, args):
        if isinstance(args, list):
            values = args
        elif isinstance(args, dict):
            values = list(args.values())
        else:
            raise TypeError("args is not list or dict")
        args = {}
        for i in range(len(values)):
            args[self.input_name[i]] = values[i]
        output = self.model.process(self.graph_name, args)
        return list(output.values())


class BmDetectorConfig(BaseDetectorConfig):
    type: Literal[DETECTOR_KEY]
    device: str = Field(default=None, title="Device Type")


class BmDetector(DetectionApi):
    type_key = DETECTOR_KEY

    def __init__(self, detector_config):
        self.model_path = detector_config.model.path

    def inference(self, tensor_input):
        data = {"images": tensor_input}  # input name from model
        engine = EngineOV(self.model_path)
        output = engine(data)
        return output
    
    def postprocess(self, results,h=320,w=320):
        if "yolov8" in self.model_path or "yolov5su" in self.model_path or "yolov5nu" in self.model_path:
            results = results[0][0, :, :]
            results = np.transpose(results)           # (n, 84)
            scores = np.max(results[:, 4:], axis=1)   # (n, )
            filtered_arg = np.argwhere(scores > 0.7)  # (n, 1)
            results = results[filtered_arg[:, 0]]
            scores = scores[filtered_arg[:, 0]]
            return self._postprocess(results,scores,h,w)
        elif "ssd" in self.model_path or "yolox" in self.model_path:
            results = results[0]
            conf = results[..., 4] > 0.7
            results = results[conf]
            results = np.delete(results, 4, axis=1)
            scores = np.max(results[..., 4:], axis=1)
            return self._postprocess(results,scores,h,w)
        elif 'yolonas' in self.model_path:
            results = np.concatenate(results, axis=-1)[0, :, :]
            scores = np.max(results[:, 4:], axis=1)   # (n, )
            filtered_arg = np.argwhere(scores > 0.7)  # (n, 1)
            results = results[filtered_arg[:, 0]]
            scores = scores[filtered_arg[:, 0]]
            return self._postprocess(results,scores,h,w)
        else:
            raise RuntimeError("not support model file:{}".format(self.model_path))
        
    def _postprocess(self, results,scores,h=320,w=320):
        num_detections = len(scores)
        if num_detections == 0:
            return np.zeros((20, 6), np.float32)
        if num_detections > 20:
            top_arg = np.argpartition(scores, -20)[-20:]
            results = results[top_arg]
            scores = scores[top_arg]
            num_detections = 20
        classes = np.argmax(results[:, 4:], axis=1)
        boxes = np.transpose(
            np.vstack(
                (
                    (results[:, 1] - 0.5 * results[:, 3]) / h,
                    (results[:, 0] - 0.5 * results[:, 2]) / w,
                    (results[:, 1] + 0.5 * results[:, 3]) / h,
                    (results[:, 0] + 0.5 * results[:, 2]) / w,
                )
            )
        )
        detections = np.zeros((20, 6), np.float32)
        detections[:num_detections, 0] = classes
        detections[:num_detections, 1] = scores
        detections[:num_detections, 2:] = boxes
        return detections

    def detect_raw(self, tensor_input):
        tensor_input = tensor_input.transpose((0,3,1,2))
        tensor_input = tensor_input.astype(np.float32)
        tensor_input = tensor_input / 255.
        results = self.inference(tensor_input)
        detections = self.postprocess(results)
        return detections
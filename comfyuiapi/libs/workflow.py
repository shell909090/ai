#!/usr/bin/env python3
"""
ComfyUI workflow wrapper

@date: 2026-01-08
@author: Shell.Xu
@copyright: 2026, Shell.Xu <shell909090@gmail.com>
@license: BSD-3-clause
"""

from comfy_api_simplified import ComfyApiWrapper, ComfyWorkflowWrapper

# Re-export ComfyApiWrapper for convenience
__all__ = ["ComfyApiWrapper", "ComfyWorkflow"]


class ComfyWorkflow(ComfyWorkflowWrapper):
    """
    ComfyUI workflow wrapper class

    Extends ComfyWorkflowWrapper from comfy-api-simplified to provide
    a dict-based initialization interface for workflow data.
    """

    def __init__(self, data: dict) -> None:
        """
        Initialize workflow with data dictionary

        Args:
            data: Workflow data as a dictionary (from JSON)
        """
        dict.__init__(self, data)

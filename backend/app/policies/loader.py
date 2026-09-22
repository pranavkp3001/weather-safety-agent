import os
import yaml
from pathlib import Path
from backend.app.policies.models import SOPDefinition, SOPContainer


def load_sops() -> list[SOPDefinition]:
    """
    Load SOPs from YAML configuration file.
    
    Returns:
        List of SOPDefinition objects loaded from sops.yaml
        
    Raises:
        FileNotFoundError: If sops.yaml cannot be found
        ValueError: If YAML is invalid or missing required fields
    """
    # Get the path to sops.yaml relative to this file
    current_dir = Path(__file__).parent
    sops_file = current_dir / "sops.yaml"
    
    if not sops_file.exists():
        raise FileNotFoundError(f"SOP configuration file not found: {sops_file}")
    
    try:
        with open(sops_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in sops.yaml: {e}")
    
    if not data:
        raise ValueError("sops.yaml is empty")
    
    # Validate and parse as SOPContainer
    try:
        container = SOPContainer(**data)
    except Exception as e:
        raise ValueError(f"Failed to parse SOPs from YAML: {e}")
    
    return container.sops

#!/usr/bin/env python3
"""
Sequence Validation Script - Validates sequence files against schema.
"""
import os
import sys
import yaml
import re
from pathlib import Path
from datetime import date
from jsonschema import validate, ValidationError

def extract_yaml_metadata(filepath):
    """Extract YAML metadata from a sequence file."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Extract all lines starting with ';@' and strip the prefix
        yaml_lines = []
        for line in content.split('\n'):
            if line.strip().startswith(';@'):
                # Remove ';@' prefix but preserve indentation after it
                if len(line.strip()) == 2:  # Just ';@' with no content
                    yaml_lines.append('')  # Empty line
                else:
                    yaml_line = line.strip()[2:]  # Remove ';@'
                    if yaml_line.startswith(' '):
                        yaml_line = yaml_line[1:]  # Remove one space after ';@'
                    yaml_lines.append(yaml_line)
        
        if not yaml_lines:
            return None
            
        # Join all YAML lines and parse as a single block
        yaml_content = '\n'.join(yaml_lines)
        metadata = yaml.safe_load(yaml_content)
        
        # Convert date objects to strings for JSON schema validation
        if metadata:
            for key, value in metadata.items():
                if isinstance(value, date):
                    metadata[key] = value.isoformat()
        
        return metadata
        
    except yaml.YAMLError as e:
        print(f'YAML syntax error in {filepath}: {e}')
        return False
    except Exception as e:
        print(f'Error parsing {filepath}: {e}')
        return False

def validate_yaml_syntax():
    """Validate YAML syntax in all sequence files."""
    print("Validating YAML syntax in sequence files...")
    
    sequences_dir = Path("sequences")
    if not sequences_dir.exists():
        print("No sequences directory found")
        return True
    
    error_count = 0
    for file_path in sequences_dir.iterdir():
        if file_path.is_file() and file_path.name != 'README.md':
            result = extract_yaml_metadata(file_path)
            if result is False:  # Syntax error occurred
                error_count += 1
            elif result is None:
                print(f"Warning: No metadata found in {file_path}")
            else:
                print(f"✓ {file_path} - Valid YAML syntax")
    
    if error_count > 0:
        print(f"YAML syntax validation failed: {error_count} files have errors")
        return False
    
    print("All YAML syntax validation passed!")
    return True

def validate_against_schema():
    """Validate all sequence files against the schema."""
    print("Validating sequences against schema...")
    
    # Load current schema
    try:
        with open('schemas/current', 'r') as f:
            schema_content = yaml.safe_load(f)
    except FileNotFoundError:
        try:
            with open('schemas/v0.0.3.yaml', 'r') as f:
                schema_content = yaml.safe_load(f)
        except FileNotFoundError:
            print("Error: No schema file found")
            return False
    
    # Find all sequence files
    sequences_dir = Path("sequences")
    if not sequences_dir.exists():
        print("No sequences directory found")
        return True
    
    error_count = 0
    for file_path in sequences_dir.iterdir():
        if file_path.is_file() and file_path.name != 'README.md':
            metadata = extract_yaml_metadata(file_path)
            
            if metadata is None:
                print(f'Warning: No metadata found in {file_path}')
                continue
            elif metadata is False:
                error_count += 1
                continue
            
            try:
                validate(instance=metadata, schema=schema_content)
                print(f'✓ {file_path} - Valid')
            except ValidationError as e:
                print(f'✗ {file_path} - Invalid: {e.message}')
                error_count += 1
    
    if error_count > 0:
        print(f'\nValidation failed: {error_count} files have errors')
        return False
    else:
        print('\nAll sequences validated successfully!')
        return True

def validate_annotation_files():
    """Validate standalone YAML files in the annotations/ directory against the schema."""
    print("Validating annotation files...")

    annotations_dir = Path("annotations")
    if not annotations_dir.exists():
        print("No annotations directory found")
        return True

    # Load schema (reuse same lookup as validate_against_schema)
    schema_content = None
    for schema_path in ['schemas/current', 'schemas/v0.0.3.yaml']:
        try:
            with open(schema_path, 'r') as f:
                schema_content = yaml.safe_load(f)
            break
        except FileNotFoundError:
            continue
    if schema_content is None:
        print("Error: No schema file found")
        return False

    error_count = 0
    yaml_files = sorted(annotations_dir.glob("*.yaml"))
    if not yaml_files:
        print("No annotation files found")
        return True

    for file_path in yaml_files:
        try:
            with open(file_path, 'r') as f:
                metadata = yaml.safe_load(f)

            if not isinstance(metadata, dict):
                print(f"✗ {file_path} - Not a valid YAML mapping")
                error_count += 1
                continue

            # Convert date objects to strings for JSON schema validation
            for key, value in metadata.items():
                if isinstance(value, date):
                    metadata[key] = value.isoformat()

            try:
                validate(instance=metadata, schema=schema_content)
                print(f"✓ {file_path} - Valid")
            except ValidationError as e:
                print(f"✗ {file_path} - Invalid: {e.message}")
                error_count += 1

        except yaml.YAMLError as e:
            print(f"✗ {file_path} - YAML syntax error: {e}")
            error_count += 1
        except Exception as e:
            print(f"✗ {file_path} - Error: {e}")
            error_count += 1

    if error_count > 0:
        print(f"\nAnnotation validation failed: {error_count} files have errors")
        return False

    print("All annotation files validated successfully!")
    return True


def check_naming_conventions():
    """Check file naming conventions."""
    print("Checking file naming conventions...")
    
    sequences_dir = Path("sequences")
    if not sequences_dir.exists():
        print("No sequences directory found")
        return True
    
    error_count = 0
    for file_path in sequences_dir.iterdir():
        if file_path.is_file() and file_path.name != 'README.md':
            filename = file_path.name
            # Allow letters, numbers, underscores, dots, and hyphens
            if not re.match(r'^[a-zA-Z0-9_.-]+$', filename):
                print(f"❌ Invalid filename: {file_path} (should contain only letters, numbers, underscores, dots, and hyphens)")
                error_count += 1
            else:
                print(f"✓ {file_path} - Valid filename")
    
    if error_count > 0:
        print(f"Naming convention check failed: {error_count} files have invalid names")
        return False
    
    print("All filename checks passed!")
    return True

def main():
    """Run all validation checks."""
    success = True
    
    # Run YAML syntax validation
    if not validate_yaml_syntax():
        success = False

    # Run schema validation
    if not validate_against_schema():
        success = False

    # Validate standalone annotation files
    if not validate_annotation_files():
        success = False

    # Run naming convention checks
    if not check_naming_conventions():
        success = False
    
    if not success:
        sys.exit(1)
    
    print("\n🎉 All validation checks passed!")

if __name__ == "__main__":
    main()
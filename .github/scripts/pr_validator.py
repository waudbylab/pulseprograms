#!/usr/bin/env python3
"""
PR Validation Script - Provides educational feedback and auto-injection suggestions.
"""
import os
import re
import yaml
import json
import subprocess
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Tuple
from jsonschema import validate, ValidationError

class PRValidator:
    def __init__(self):
        self.repo_info = self.get_repo_info()
        self.schema = self.load_schema()
        self.validation_results = []
        self.suggestions = []
        
    def get_repo_info(self) -> Dict[str, str]:
        """Extract repository information from Git and GitHub."""
        info = {
            'url': 'github.com/waudbylab/pulseprograms',
            'name': 'pulseprograms',
            'author_name': 'Your Name',
            'author_email': 'email@institution.edu'
        }
        
        try:
            # Get repository URL from git remote
            result = subprocess.run(['git', 'remote', 'get-url', 'origin'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                remote_url = result.stdout.strip()
                # Convert SSH/HTTPS URL to github.com format
                if 'github.com' in remote_url:
                    repo_path = remote_url.split('github.com')[1].strip('/:').replace('.git', '')
                    info['url'] = f"github.com/{repo_path}"
                    info['name'] = repo_path.split('/')[-1]
            
            # Try to get contributor info from environment variables (GitHub Actions context)
            pr_author = os.environ.get('PR_AUTHOR')
            if pr_author:
                info['author_name'] = pr_author
                
                # Try to get email from GitHub API
                github_token = os.environ.get('GITHUB_TOKEN')
                if github_token:
                    try:
                        import requests
                        headers = {
                            'Authorization': f'token {github_token}',
                            'Accept': 'application/vnd.github.v3+json'
                        }
                        response = requests.get(f'https://api.github.com/users/{pr_author}', headers=headers)
                        if response.status_code == 200:
                            user_data = response.json()
                            if user_data.get('email'):
                                info['author_email'] = user_data['email']
                            if user_data.get('name'):
                                info['author_name'] = user_data['name']
                            # Don't set a fake email if we can't get a real one
                    except:
                        pass  # Keep defaults
            
            # Fallback: try git config (won't work in CI but good for local testing)
            if info['author_name'] == 'Your Name':
                name_result = subprocess.run(['git', 'config', 'user.name'], 
                                           capture_output=True, text=True)
                if name_result.returncode == 0 and name_result.stdout.strip():
                    info['author_name'] = name_result.stdout.strip()
            
            if info['author_email'] == 'email@institution.edu':
                email_result = subprocess.run(['git', 'config', 'user.email'], 
                                            capture_output=True, text=True)
                if email_result.returncode == 0 and email_result.stdout.strip():
                    info['author_email'] = email_result.stdout.strip()
            
        except:
            pass
        
        return info
    
    def load_schema(self) -> Dict[str, Any]:
        """Load the current schema."""
        schema_file = Path("schemas/current")
        if not schema_file.exists():
            schema_file = Path("schemas/v0.0.3.yaml")
        
        with open(schema_file, 'r') as f:
            return yaml.safe_load(f)
    
    def get_changed_files(self) -> List[str]:
        """Get list of changed sequence and annotation files in this PR."""
        try:
            # Get files changed in PR (compared to base branch)
            result = subprocess.run(['git', 'diff', '--name-only', 'origin/main...HEAD'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                changed_files = []
                for file in result.stdout.strip().split('\n'):
                    if file.startswith('sequences/') and not file.endswith('README.md'):
                        changed_files.append(file)
                    elif file.startswith('annotations/') and file.endswith('.yaml'):
                        changed_files.append(file)
                return changed_files
        except:
            pass

        # Fallback: check all sequence and annotation files
        changed_files = []
        sequences_dir = Path("sequences")
        if sequences_dir.exists():
            changed_files += [str(f) for f in sequences_dir.iterdir()
                              if f.is_file() and f.name != 'README.md']
        annotations_dir = Path("annotations")
        if annotations_dir.exists():
            changed_files += [str(f) for f in annotations_dir.glob("*.yaml")]
        return changed_files
    
    def extract_metadata(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Extract YAML metadata from a sequence or annotation file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Annotation files are plain YAML; sequence files use ';@' prefix
            if file_path.startswith('annotations/'):
                metadata = yaml.safe_load(content)
            else:
                yaml_lines = []
                for line in content.split('\n'):
                    if line.strip().startswith(';@'):
                        if len(line.strip()) == 2:
                            yaml_lines.append('')
                        else:
                            yaml_line = line.strip()[2:]
                            if yaml_line.startswith(' '):
                                yaml_line = yaml_line[1:]
                            yaml_lines.append(yaml_line)

                if not yaml_lines:
                    return None

                metadata = yaml.safe_load('\n'.join(yaml_lines))

            if not isinstance(metadata, dict):
                return None

            # Convert date objects to strings for validation
            for key, value in metadata.items():
                if isinstance(value, date):
                    metadata[key] = value.isoformat()

            return metadata

        except Exception:
            return None
    
    def generate_auto_suggestions(self, file_path: str, metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate consolidated auto-injection suggestions."""
        file_name = Path(file_path).name
        suggestions = {
            'missing_required': [],
            'suggested_metadata': {},
            'improvements': [],
            'optional_recommendations': []
        }
        
        if metadata is None:
            # Complete metadata template for files with no annotations
            author_name = self.repo_info["author_name"]
            author_email = self.repo_info["author_email"]
            
            if author_email != 'email@institution.edu':
                # We have a real email
                authors_value = f'[{author_name} <{author_email}>]'
            else:
                # No real email, just use name
                authors_value = f'[{author_name}]'
            
            complete_template = {
                'schema_version': '"0.0.3"',
                'sequence_version': '"0.1.0"',
                'title': f'"{file_name}"',
                'authors': authors_value,
                'created': f'"{date.today().isoformat()}"',
                'last_modified': f'"{date.today().isoformat()}"',
                'repository': f'"{self.repo_info["url"]}"',
                'status': 'experimental'
            }
            
            suggestions['complete_template'] = complete_template
            return suggestions
        
        # Check for missing required fields
        required_fields = self.schema.get('required', [])
        missing_required = []
        suggested_additions = {}
        
        for field in required_fields:
            if field not in metadata:
                missing_required.append(field)
                suggested_additions[field] = self.get_default_value(field, file_name)
        
        suggestions['missing_required'] = missing_required
        suggestions['suggested_metadata'] = suggested_additions
        
        # Field improvements
        if 'title' in metadata and metadata['title'] == file_name:
            suggestions['improvements'].append({
                'field': 'title',
                'current': metadata['title'],
                'suggestion': 'Consider a more descriptive title',
                'example': '"Descriptive Sequence Name"'
            })
        
        # Only suggest experiment_type and description as key optional fields
        key_optional_fields = {}
        
        if 'experiment_type' not in metadata:
            key_optional_fields['experiment_type'] = {
                'description': 'Keywords describing the experiment type',
                'examples': ['hsqc', '2d', 'cosy', 'tocsy', 'noesy', 'relaxation', '1d', 'cest']
            }
        
        if 'description' not in metadata:
            key_optional_fields['description'] = {
                'description': 'Brief description of what this sequence does',
                'examples': []
            }
        
        if key_optional_fields:
            suggestions['key_optional_fields'] = key_optional_fields
        
        return suggestions
    
    def get_default_value(self, field: str, file_name: str) -> str:
        """Get appropriate default value for a field."""
        # Handle authors field specially based on available info
        if field == 'authors':
            author_name = self.repo_info["author_name"]
            author_email = self.repo_info["author_email"]
            
            if author_email != 'email@institution.edu':
                # We have a real email
                return f'[{author_name} <{author_email}>]'
            else:
                # No real email, just use name
                return f'[{author_name}]'
        
        defaults = {
            'schema_version': '"0.0.3"',
            'sequence_version': '"0.1.0"',
            'title': f'"{file_name}"',
            'created': f'"{date.today().isoformat()}"',
            'last_modified': f'"{date.today().isoformat()}"',
            'repository': f'"{self.repo_info["url"]}"',
            'status': 'experimental'
        }
        return defaults.get(field, '""')
    
    def validate_sequence(self, file_path: str) -> Dict[str, Any]:
        """Validate a single sequence or annotation file."""
        file_name = Path(file_path).name
        result = {
            'file': file_path,
            'is_annotation': file_path.startswith('annotations/'),
            'valid': False,
            'errors': [],
            'warnings': [],
            'suggestions': []
        }
        
        # Extract metadata
        metadata = self.extract_metadata(file_path)
        
        if metadata is None:
            result['errors'].append("No YAML metadata found")
            result['suggestions'] = self.generate_auto_suggestions(file_path, None)
            return result
        
        # Validate against schema
        try:
            validate(instance=metadata, schema=self.schema)
            result['valid'] = True
        except ValidationError as e:
            result['errors'].append(f"Schema validation failed: {e.message}")
        
        # Generate suggestions
        result['suggestions'] = self.generate_auto_suggestions(file_path, metadata)
        
        # Check for common issues and warnings (but avoid duplicating what's in suggestions)
        suggestions_dict = result['suggestions']
        key_optional_suggested = suggestions_dict.get('key_optional_fields', {})
        
        # Only warn about missing fields if we're not already suggesting them
        if 'experiment_type' not in metadata and 'experiment_type' not in key_optional_suggested:
            result['warnings'].append("Missing experiment_type - adds discoverability")
        
        if 'description' not in metadata and 'description' not in key_optional_suggested:
            result['warnings'].append("Missing description - helps users understand the sequence")
        
        # Check for outdated dates
        if 'last_modified' in metadata:
            try:
                from datetime import datetime
                last_modified = datetime.fromisoformat(metadata['last_modified'])
                today = datetime.now()
                days_old = (today - last_modified).days
                if days_old > 30:  # Flag if last_modified is more than 30 days old
                    result['warnings'].append(f"Last modified date is {days_old} days old - consider updating if this sequence has changed")
            except:
                pass
        
        # Check for version number consistency and bumping
        if 'sequence_version' in metadata:
            version = metadata['sequence_version']
            
            # Basic version format check
            if not re.match(r'^\d+\.\d+\.\d+$', version):
                result['warnings'].append("Sequence version should follow semantic versioning (e.g., 1.0.0)")
            elif version == "0.0.0":
                result['warnings'].append("Consider using a proper version number instead of 0.0.0")
            else:
                # Check if this is a file update and version needs bumping
                previous_version = self.get_previous_version(file_path)
                if previous_version and self.is_file_modified(file_path):
                    if version == previous_version:
                        result['warnings'].append(f"File has been modified but version is still {version} - consider bumping to indicate changes")
                    elif not self.is_version_newer(version, previous_version):
                        result['warnings'].append(f"Version {version} is not newer than previous version {previous_version}")
            
        elif self.is_file_modified(file_path) and 'sequence_version' not in suggestions_dict.get('missing_required', []):
            # File modified but no version field at all - only warn if not already suggesting it
            result['warnings'].append("File has been modified - consider adding a sequence_version field")
        
        return result
    
    def get_previous_version(self, file_path: str) -> Optional[str]:
        """Get the sequence_version from the previous version of the file in git."""
        try:
            result = subprocess.run(['git', 'show', f'origin/main:{file_path}'],
                                  capture_output=True, text=True)
            if result.returncode != 0:
                return None

            content = result.stdout

            if file_path.startswith('annotations/'):
                metadata = yaml.safe_load(content)
            else:
                yaml_lines = []
                for line in content.split('\n'):
                    if line.strip().startswith(';@'):
                        if len(line.strip()) == 2:
                            yaml_lines.append('')
                        else:
                            yaml_line = line.strip()[2:]
                            if yaml_line.startswith(' '):
                                yaml_line = yaml_line[1:]
                            yaml_lines.append(yaml_line)

                if not yaml_lines:
                    return None

                metadata = yaml.safe_load('\n'.join(yaml_lines))

            if isinstance(metadata, dict) and 'sequence_version' in metadata:
                return metadata['sequence_version']

        except Exception:
            pass

        return None
    
    def is_file_modified(self, file_path: str) -> bool:
        """Check if the file has been modified compared to the base branch."""
        try:
            # Compare file with base branch
            result = subprocess.run(['git', 'diff', '--quiet', f'origin/main...HEAD', '--', file_path], 
                                  capture_output=True)
            # Returns 0 if no differences, 1 if differences found
            return result.returncode != 0
        except Exception:
            # If we can't determine, assume it's modified to be safe
            return True
    
    def is_version_newer(self, current_version: str, previous_version: str) -> bool:
        """Check if current version is newer than previous version using semantic versioning."""
        try:
            def parse_version(version_str):
                return tuple(int(x) for x in version_str.split('.'))
            
            current_parts = parse_version(current_version)
            previous_parts = parse_version(previous_version)
            
            return current_parts > previous_parts
        except Exception:
            # If we can't parse versions, assume current is newer to avoid false warnings
            return True
    
    def validate_all_changed_files(self) -> List[Dict[str, Any]]:
        """Validate all changed sequence files."""
        changed_files = self.get_changed_files()
        results = []
        
        for file_path in changed_files:
            if os.path.exists(file_path):
                result = self.validate_sequence(file_path)
                results.append(result)
        
        return results
    
    def generate_pr_comment(self, results: List[Dict[str, Any]]) -> str:
        """Generate markdown comment for PR with consolidated suggestions."""
        if not results:
            return """
## 🎉 PR Validation Results

No sequence files were changed in this PR.
"""
        
        # Count statistics
        total_files = len(results)
        valid_files = sum(1 for r in results if r['valid'])
        files_with_errors = sum(1 for r in results if r['errors'])
        files_with_suggestions = sum(1 for r in results if r['suggestions'])
        
        comment = f"""
## 🔍 PR Validation Results

**Files processed:** {total_files} | **Valid:** {valid_files} | **With errors:** {files_with_errors} | **With suggestions:** {files_with_suggestions}

"""
        
        # Add status for each file
        for result in results:
            file_name = Path(result['file']).name
            suggestions = result.get('suggestions', {})
            
            if result['valid'] and not result['errors']:
                status_icon = "✅"
                status_text = "Valid"
            else:
                status_icon = "❌" 
                status_text = "Issues found"
            
            comment += f"### {status_icon} `{file_name}` - {status_text}\n\n"
            
            # Show current metadata first (if any exists)
            metadata = None
            if not result['errors'] or 'No YAML metadata found' not in str(result['errors']):
                # Try to extract metadata to show what's currently there
                try:
                    metadata = self.extract_metadata(result['file'])
                except:
                    pass
            
            if metadata:
                comment += "**📋 Current Metadata:**\n"
                for key, value in sorted(metadata.items()):
                    if not key.startswith('_'):  # Skip internal fields
                        if isinstance(value, list):
                            value_str = ', '.join(str(v) for v in value)
                        else:
                            value_str = str(value)
                        comment += f"- `{key}`: {value_str}\n"
                comment += "\n"
            
            # Show errors first (highest priority)
            if result['errors']:
                comment += "**❌ Required Actions:**\n"
                for error in result['errors']:
                    comment += f"- {error}\n"
                comment += "\n"
            
            # Annotation files use plain YAML; sequence files use ;@ prefix
            field_prefix = "" if result.get('is_annotation') else ";@ "

            # Handle complete template for files with no metadata
            if 'complete_template' in suggestions:
                comment += "**📝 Add This Metadata (Copy & Paste):**\n\n"
                comment += "```yaml\n"
                for field, value in suggestions['complete_template'].items():
                    comment += f"{field_prefix}{field}: {value}\n"
                comment += "```\n\n"

            # Handle missing required fields
            elif suggestions.get('missing_required'):
                missing_fields = suggestions['missing_required']
                suggested_metadata = suggestions.get('suggested_metadata', {})

                comment += "**📝 Add Missing Required Fields:**\n\n"
                comment += "```yaml\n"
                for field in missing_fields:
                    value = suggested_metadata.get(field, '""')
                    comment += f"{field_prefix}{field}: {value}\n"
                comment += "```\n\n"
            
            # Handle key optional fields (experiment_type and description only)
            if suggestions.get('key_optional_fields'):
                optional_fields = suggestions['key_optional_fields']
                comment += "**💡 Recommended Optional Fields:**\n\n"
                
                for field, info in optional_fields.items():
                    if field == 'experiment_type':
                        examples_str = ', '.join(f"`{ex}`" for ex in info['examples'][:6])  # Limit examples
                        comment += f"- **`{field}`**: {info['description']} (e.g., {examples_str})\n"
                    else:  # description
                        comment += f"- **`{field}`**: {info['description']}\n"
                comment += "\n"
            
            # Add warnings at the end (lowest priority)
            if result['warnings']:
                comment += "**⚠️ Suggestions:**\n"
                for warning in result['warnings']:
                    comment += f"- {warning}\n"
                comment += "\n"
            
            comment += "---\n\n"
        
        # Add footer with helpful information
        author_display = self.repo_info['author_name']
        if self.repo_info['author_email'] != 'email@institution.edu':
            author_display += f" <{self.repo_info['author_email']}>"
        
        comment += f"""
## 📚 Resources

- **All optional fields:** See the [schema documentation](https://github.com/{self.repo_info['name']}/blob/main/schemas/current) for complete field list
- **Contributing guide:** Check [CONTRIBUTING.md](https://github.com/{self.repo_info['name']}/blob/main/CONTRIBUTING.md) for detailed instructions
- **Examples:** Browse existing sequences for annotation patterns

💡 **Need help?** Open an issue or check our contributing guidelines for detailed instructions.

---
*This validation was performed automatically. The suggestions above are meant to be helpful - not all are required for your PR to be accepted.*

**Detected contributor:** {author_display}
"""
        
        return comment

def main():
    validator = PRValidator()
    results = validator.validate_all_changed_files()
    comment = validator.generate_pr_comment(results)
    
    # Save comment to file for GitHub Action to use
    with open('pr_comment.md', 'w') as f:
        f.write(comment)
    
    # Print summary
    total_files = len(results)
    valid_files = sum(1 for r in results if r['valid'])
    print(f"Validated {total_files} files. {valid_files} valid, {total_files - valid_files} with issues.")
    
    # Exit with error code if there are validation errors (optional - you might want to allow PRs with suggestions)
    # has_errors = any(r['errors'] for r in results)
    # if has_errors:
    #     exit(1)

if __name__ == "__main__":
    main()
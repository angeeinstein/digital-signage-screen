# Contributing to Digital Signage Display

Thank you for your interest in contributing! 🎉

## Development Setup

1. Fork the repository
2. Clone your fork:
```bash
git clone https://github.com/YOUR-USERNAME/digital-signage-screen.git
cd digital-signage-screen
```

3. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

4. Run development server:
```bash
python app.py
```

## Making Changes

1. Create a new branch:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes
3. Test your changes thoroughly
4. Commit with clear messages:
```bash
git commit -m "Add: description of your changes"
```

5. Push to your fork:
```bash
git push origin feature/your-feature-name
```

6. Create a Pull Request

## Testing on Raspberry Pi

Test the full installation process:
```bash
sudo bash install.sh
```

Test updates:
```bash
sudo bash install.sh  # Choose option 1
```

## Code Style

- Follow PEP 8 for Python code
- Use meaningful variable names
- Add comments for complex logic
- Keep functions focused and small

## Pull Request Guidelines

- Describe your changes clearly
- Reference any related issues
- Ensure all tests pass
- Update documentation if needed
- Add yourself to CONTRIBUTORS.md (if it exists)

## Reporting Issues

When reporting issues, please include:
- Raspberry Pi model and OS version
- Python version
- Error messages and logs
- Steps to reproduce

## Questions?

Feel free to open an issue for questions or discussions!

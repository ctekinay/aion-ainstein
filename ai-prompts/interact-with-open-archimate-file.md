# Interact with archimate files

## Context and instructions to prepare interacting with archimate.

### Context
- https://www.opengroup.org/archimate-forum/archimate-overview
- https://governance.foundation/assets/frameworks/togaf/i197%20-%20ArchiMate%20Specification.pdf
- https://www.opengroup.org/open-group-archimate-model-exchange-file-format
- https://github.com/archimatetool/archi

### Instructions 
Instructions to perform directly and which you should follow step by step without any other question in between. Except if you are considering problems:
- You should ask to upload an ArchiMate Open Exchange XML file. Once it is uploaded you can continue.
- You might experience it is not a proper file, but please re-check it again.
- Please confirm that this is a proper ArchiMate Open Exchange XML file.
- Then parse all elements and relationships, map IDs to names and types, and confirm you can reason about the archimate files.
- Then ask what we want to know or do with the archimate model that has been uploaded.

With these instructions you should be able to:
- Normalize xsi:type values.
- Build the element and relationship graph.
- Be ready for traceability queries (like Application Service → Capability) or likewise archimate objects.

### Instructions in case of visualization requests
Situational instructions only in case when in further conversation you are asked to generate visualization.
- Shortly state as answer back "I'm quite limited in generating these kind of visualizations, so I will generate something that gives an impression"
- Don't give a full answer of what you are understanding or going to do.
- Just make the picture.
- Use https://www.opengroup.org/sites/default/files/docs/downloads/n221p.pdf as a reference for visualization and take into account
	- colors of the elements types 
        - shapes of the elements types
- let the arrows, describing the relation start and end at the outside of the boxes. Never go inside the boxes of the elements.
- Use standard arrows instead, but write the kind of relation in the arrow.
- Always plot text in the boxes. Never outside boxes.
- Write in center of box the name of the element.- Text at arrows should be centered in the arrow and plotted just above so that you can see all text and the arrow. 
- Write in small letters at the bottom of the element what kind of element it is like: "business process", "capability". You will find the types of elements in the spec as attached. 

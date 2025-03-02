import numpy as np
import moderngl
from pygltflib import GLTF2
import base64
import os
import struct
from PIL import Image
import io

# OpenGL constants for texture parameters
# Filters
GL_NEAREST = 9728
GL_LINEAR = 9729
GL_NEAREST_MIPMAP_NEAREST = 9984
GL_LINEAR_MIPMAP_NEAREST = 9985
GL_NEAREST_MIPMAP_LINEAR = 9986
GL_LINEAR_MIPMAP_LINEAR = 9987
# Wrapping modes
GL_CLAMP_TO_EDGE = 33071
GL_MIRRORED_REPEAT = 33648
GL_REPEAT = 10497

def load_gltf(ctx, file_path):
    """
    Load a GLTF file and prepare it for rendering with ModernGL.
    
    Args:
        ctx: The ModernGL context
        file_path: Path to the GLTF file
        
    Returns:
        Dictionary containing the loaded model data and rendering information
    """
    # Load the GLTF file
    gltf = GLTF2().load(file_path)
    
    model_dir = os.path.dirname(file_path)
    
    # Dictionary to store the model data
    model = {
        'meshes': [],
        'buffers': [],
        'images': [],
        'textures': [],
        'samplers': []
    }
    
    # Load buffers
    for i, buffer in enumerate(gltf.buffers):
        if hasattr(buffer, 'uri') and buffer.uri:
            if buffer.uri.startswith('data:'):
                # Handle embedded buffer (data URI)
                _, data_str = buffer.uri.split(',', 1)
                data = base64.b64decode(data_str)
                model['buffers'].append(data)
            else:
                # Handle external buffer file
                buffer_path = os.path.join(model_dir, buffer.uri)
                with open(buffer_path, 'rb') as f:
                    model['buffers'].append(f.read())
        else:
            # Handle GLB buffer (already embedded in the GLTF file)
            model['buffers'].append(gltf.binary_blob())
    
    # Process samplers
    for i, sampler in enumerate(gltf.samplers):
        # Default values according to GLTF spec
        mag_filter = GL_LINEAR
        min_filter = GL_LINEAR_MIPMAP_LINEAR
        wrap_s = GL_REPEAT
        wrap_t = GL_REPEAT
        
        if hasattr(sampler, 'magFilter') and sampler.magFilter is not None:
            mag_filter = sampler.magFilter
        if hasattr(sampler, 'minFilter') and sampler.minFilter is not None:
            min_filter = sampler.minFilter
        if hasattr(sampler, 'wrapS') and sampler.wrapS is not None:
            wrap_s = sampler.wrapS
        if hasattr(sampler, 'wrapT') and sampler.wrapT is not None:
            wrap_t = sampler.wrapT
        
        model['samplers'].append({
            'magFilter': mag_filter,
            'minFilter': min_filter,
            'wrapS': wrap_s,
            'wrapT': wrap_t
        })
    
    # Load images
    for i, image in enumerate(gltf.images):
        if hasattr(image, 'uri') and image.uri:
            if image.uri.startswith('data:'):
                # Handle embedded image (data URI)
                _, data_str = image.uri.split(',', 1)
                data = base64.b64decode(data_str)
                img = Image.open(io.BytesIO(data))
            else:
                # Handle external image file
                image_path = os.path.join(model_dir, image.uri)
                img = Image.open(image_path)
            
            # Convert to RGBA if needed
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Flip the image vertically AND horizontally for correct orientation
            # This is fixing the texture orientation issue
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
            
            # Get image data as bytes
            img_data = img.tobytes()
            
            # Create a texture
            texture = ctx.texture(img.size, 4, img_data)
            
            model['images'].append(texture)
    
    # Process textures by connecting samplers with images
    for i, texture in enumerate(gltf.textures):
        sampler_index = 0  # Default to first sampler if not specified
        if hasattr(texture, 'sampler') and texture.sampler is not None:
            sampler_index = texture.sampler
        
        image_index = texture.source
        
        # Ensure indices are valid
        if sampler_index < len(model['samplers']) and image_index < len(model['images']):
            # Get the sampler and image
            sampler = model['samplers'][sampler_index]
            texture_obj = model['images'][image_index]
            
            # Apply sampler parameters to the texture
            texture_obj.filter = (sampler['magFilter'], sampler['minFilter'])
            texture_obj.repeat_x = True if sampler['wrapS'] == GL_REPEAT else False
            texture_obj.repeat_y = True if sampler['wrapT'] == GL_REPEAT else False
            
            # Build mipmaps if using mipmapping
            if sampler['minFilter'] in [GL_NEAREST_MIPMAP_NEAREST, GL_LINEAR_MIPMAP_NEAREST, 
                                   GL_NEAREST_MIPMAP_LINEAR, GL_LINEAR_MIPMAP_LINEAR]:
                texture_obj.build_mipmaps()
            
            # Store the configured texture
            model['textures'].append(texture_obj)
        else:
            # If indices are invalid, still add something to maintain indices
            model['textures'].append(None)
    
    # Create shaders
    vertex_shader = '''
        #version 330
        
        uniform mat4 model;
        uniform mat4 view;
        uniform mat4 projection;
        
        in vec3 in_position;
        in vec3 in_normal;
        in vec2 in_texcoord_0;
        
        out vec3 normal;
        out vec2 texcoord_0;
        out vec3 position;
        out vec3 world_position;
        
        void main() {
            world_position = vec3(model * vec4(in_position, 1.0));
            position = vec3(view * vec4(world_position, 1.0));
            normal = mat3(transpose(inverse(model))) * in_normal;
            texcoord_0 = in_texcoord_0;
            gl_Position = projection * view * model * vec4(in_position, 1.0);
        }
    '''

    fragment_shader = '''
        #version 330
        
        uniform vec4 baseColorFactor;
        uniform sampler2D baseColorTexture;
        uniform bool hasBaseColorTexture;
        
        in vec3 normal;
        in vec2 texcoord_0;
        in vec3 position;
        in vec3 world_position;
        
        out vec4 fragColor;
        
        void main() {
            // Normalize the normal vector
            vec3 norm = normalize(normal);
            
            // Multiple light positions for better texture visibility
            vec3 lightPos1 = vec3(5.0, 8.0, 5.0);
            vec3 lightPos2 = vec3(-5.0, 5.0, -2.0); // Back light
            vec3 lightPos3 = vec3(0.0, 3.0, 8.0);   // Front light
            
            vec3 lightColor1 = vec3(1.0, 0.9, 0.8); // Warm main light
            vec3 lightColor2 = vec3(0.6, 0.7, 1.0); // Cool back light
            vec3 lightColor3 = vec3(0.9, 0.9, 1.0); // Neutral fill light
            
            // Ambient lighting - brighter for better texture visibility
            float ambientStrength = 0.45;
            vec3 ambient = ambientStrength * vec3(1.0, 1.0, 1.0);
            
            // Calculate diffuse lighting for each light
            vec3 lightDir1 = normalize(lightPos1 - world_position);
            float diff1 = max(dot(norm, lightDir1), 0.0);
            vec3 diffuse1 = diff1 * lightColor1;
            
            vec3 lightDir2 = normalize(lightPos2 - world_position);
            float diff2 = max(dot(norm, lightDir2), 0.0);
            vec3 diffuse2 = diff2 * lightColor2 * 0.5; // Dimmer back light
            
            vec3 lightDir3 = normalize(lightPos3 - world_position);
            float diff3 = max(dot(norm, lightDir3), 0.0);
            vec3 diffuse3 = diff3 * lightColor3 * 0.7; // Medium fill light
            
            // Combine lighting
            vec3 lighting = ambient + diffuse1 + diffuse2 + diffuse3;
            
            // Get base color from material and/or texture
            vec4 baseColor = baseColorFactor;
            if (hasBaseColorTexture) {
                // Sample the texture with the corrected UV coordinates
                baseColor *= texture(baseColorTexture, texcoord_0);
            }
            
            // Apply lighting to the color with a slight boost to saturation
            vec3 finalColor = lighting * baseColor.rgb;
            
            // Output final color with original alpha
            fragColor = vec4(finalColor, baseColor.a);
        }
    '''
    
    # Create program
    program = ctx.program(
        vertex_shader=vertex_shader,
        fragment_shader=fragment_shader
    )
    
    # Process meshes
    for mesh_index, mesh in enumerate(gltf.meshes):
        for primitive_index, primitive in enumerate(mesh.primitives):
            # Get material
            material = None
            if primitive.material >= 0 and primitive.material < len(gltf.materials):
                material = gltf.materials[primitive.material]
            
            # Get indices
            indices = None
            if primitive.indices is not None:
                indices_accessor = gltf.accessors[primitive.indices]
                indices_buffer_view = gltf.bufferViews[indices_accessor.bufferView]
                indices_buffer = model['buffers'][indices_buffer_view.buffer]
                
                # Get the byte offset
                byte_offset = indices_buffer_view.byteOffset if hasattr(indices_buffer_view, 'byteOffset') else 0
                if hasattr(indices_accessor, 'byteOffset') and indices_accessor.byteOffset:
                    byte_offset += indices_accessor.byteOffset
                
                # Calculate the count and component type
                count = indices_accessor.count
                component_type = indices_accessor.componentType
                
                # Extract indices based on component type
                if component_type == 5121:  # GL_UNSIGNED_BYTE
                    indices = np.frombuffer(
                        indices_buffer,
                        dtype=np.uint8,
                        count=count,
                        offset=byte_offset
                    )
                elif component_type == 5123:  # GL_UNSIGNED_SHORT
                    indices = np.frombuffer(
                        indices_buffer,
                        dtype=np.uint16,
                        count=count,
                        offset=byte_offset
                    )
                elif component_type == 5125:  # GL_UNSIGNED_INT
                    indices = np.frombuffer(
                        indices_buffer,
                        dtype=np.uint32,
                        count=count,
                        offset=byte_offset
                    )
            
            # Get vertex positions
            vertices = None
            if hasattr(primitive.attributes, 'POSITION'):
                position_accessor = gltf.accessors[primitive.attributes.POSITION]
                position_buffer_view = gltf.bufferViews[position_accessor.bufferView]
                position_buffer = model['buffers'][position_buffer_view.buffer]
                
                # Get byte offset
                byte_offset = position_buffer_view.byteOffset if hasattr(position_buffer_view, 'byteOffset') else 0
                if hasattr(position_accessor, 'byteOffset') and position_accessor.byteOffset:
                    byte_offset += position_accessor.byteOffset
                
                # Calculate count and extract vertices
                count = position_accessor.count
                vertices = np.frombuffer(
                    position_buffer,
                    dtype=np.float32,
                    count=count * 3,
                    offset=byte_offset
                ).reshape(count, 3)
            
            # Get normals
            normals = None
            if hasattr(primitive.attributes, 'NORMAL'):
                normal_accessor = gltf.accessors[primitive.attributes.NORMAL]
                normal_buffer_view = gltf.bufferViews[normal_accessor.bufferView]
                normal_buffer = model['buffers'][normal_buffer_view.buffer]
                
                # Get byte offset
                byte_offset = normal_buffer_view.byteOffset if hasattr(normal_buffer_view, 'byteOffset') else 0
                if hasattr(normal_accessor, 'byteOffset') and normal_accessor.byteOffset:
                    byte_offset += normal_accessor.byteOffset
                
                # Calculate count and extract normals
                count = normal_accessor.count
                normals = np.frombuffer(
                    normal_buffer,
                    dtype=np.float32,
                    count=count * 3,
                    offset=byte_offset
                ).reshape(count, 3)
            
            # Get texture coordinates
            texcoords = None
            if hasattr(primitive.attributes, 'TEXCOORD_0'):
                texcoord_accessor = gltf.accessors[primitive.attributes.TEXCOORD_0]
                texcoord_buffer_view = gltf.bufferViews[texcoord_accessor.bufferView]
                texcoord_buffer = model['buffers'][texcoord_buffer_view.buffer]
                
                # Get byte offset
                byte_offset = texcoord_buffer_view.byteOffset if hasattr(texcoord_buffer_view, 'byteOffset') else 0
                if hasattr(texcoord_accessor, 'byteOffset') and texcoord_accessor.byteOffset:
                    byte_offset += texcoord_accessor.byteOffset
                
                # Calculate count and extract texture coordinates
                count = texcoord_accessor.count
                original_texcoords = np.frombuffer(
                    texcoord_buffer,
                    dtype=np.float32,
                    count=count * 2,
                    offset=byte_offset
                ).reshape(count, 2)
                
                # Create a new array to modify the texture coordinates
                # This avoids the read-only issue
                texcoords = np.copy(original_texcoords)
                
                # Fix texture coordinate orientation
                # Flip the V coordinate for correct texture orientation
                texcoords[:, 1] = 1.0 - texcoords[:, 1]
            
            # Create VAO with the model data
            vao_content = {}
            
            if vertices is not None:
                vao_content['in_position'] = vertices.astype('f4')
            
            if normals is not None:
                vao_content['in_normal'] = normals.astype('f4')
            
            if texcoords is not None:
                vao_content['in_texcoord_0'] = texcoords.astype('f4')
            
            # Create the VAO
            vao = ctx.vertex_array(
                program,
                [
                    (ctx.buffer(vao_content.get('in_position', np.zeros((1, 3), dtype='f4'))), '3f', 'in_position'),
                    (ctx.buffer(vao_content.get('in_normal', np.zeros((1, 3), dtype='f4'))), '3f', 'in_normal'),
                    (ctx.buffer(vao_content.get('in_texcoord_0', np.zeros((1, 2), dtype='f4'))), '2f', 'in_texcoord_0'),
                ],
                ctx.buffer(indices.astype('i4')) if indices is not None else None
            )
            
            # Material properties
            base_color_factor = [1.0, 1.0, 1.0, 1.0]
            base_color_texture = None
            
            if material is not None and hasattr(material, 'pbrMetallicRoughness'):
                pbr = material.pbrMetallicRoughness
                if hasattr(pbr, 'baseColorFactor') and pbr.baseColorFactor is not None:
                    base_color_factor = pbr.baseColorFactor
                
                if hasattr(pbr, 'baseColorTexture') and pbr.baseColorTexture is not None:
                    # Get the texture from the baseColorTexture
                    texture_index = pbr.baseColorTexture.index
                    if texture_index < len(model['textures']) and model['textures'][texture_index] is not None:
                        base_color_texture = model['textures'][texture_index]
            
            # Add the mesh to the model
            model['meshes'].append({
                'vao': vao,
                'program': program,
                'material': {
                    'baseColorFactor': base_color_factor,
                    'baseColorTexture': base_color_texture,
                    'hasBaseColorTexture': base_color_texture is not None
                },
                'indices': indices
            })
    
    return model

def render_gltf(model, model_matrix, view_matrix, projection_matrix):
    """
    Render a GLTF model with the given matrices.
    
    Args:
        model: The loaded model data
        model_matrix: The model transformation matrix
        view_matrix: The view matrix
        projection_matrix: The projection matrix
    """
    for mesh in model['meshes']:
        # Set matrices
        mesh['program']['model'].write(model_matrix.astype('f4').tobytes())
        mesh['program']['view'].write(view_matrix.astype('f4').tobytes())
        mesh['program']['projection'].write(projection_matrix.astype('f4').tobytes())
        
        # Set material uniforms
        mesh['program']['baseColorFactor'].write(np.array(mesh['material']['baseColorFactor'], dtype='f4'))
        mesh['program']['hasBaseColorTexture'].value = mesh['material']['hasBaseColorTexture']
        
        # Bind texture if it exists
        if mesh['material']['hasBaseColorTexture']:
            mesh['material']['baseColorTexture'].use(0)
            mesh['program']['baseColorTexture'].value = 0
        
        # Render the mesh
        mesh['vao'].render(moderngl.TRIANGLES) 